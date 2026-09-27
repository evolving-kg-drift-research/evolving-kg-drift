"""Ticket A readiness gate. A blocked inventory is evidence, never a passing gate."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow.parquet as pq

from .baseline import inspect_config_approval, inspect_source_lock
from .contracts import TABLE_SCHEMAS, FOREIGN_KEYS, validate_retrieval_rows
from .hashing import sha256_json, sha256_text, utc_now_iso
from .readiness import raw_input_blockers
from .run import config_fingerprints, get_run_dir, load_run_manifest, resolve_run_table_path
from .storage import read_json, read_yaml, verify_parquet_artifact, write_json_immutable

REQUIRED_TABLES = (
    "raw_inventory",
    "raw_hash_audit",
    "retrievals",
    "source_versions",
    "provenance_recovery_ledger",
    "body_variants",
    "document_memberships",
    "document_clusters",
    "lineage_edges",
    "near_duplicate_candidates",
    "missing_coverage_ledger",
    "coverage_ledger",
)


def _check(check_id: str, status: str, detail: str, evidence_path: str) -> dict[str, str]:
    return {"check_id": check_id, "status": status, "detail": detail, "evidence_path": evidence_path}


def _read_table(run_dir: Path, table_name: str) -> list[dict[str, Any]]:
    return pq.read_table(run_dir / "tables" / f"{table_name}.parquet").to_pylist()


def _persist_evaluation(run_dir: Path, result: dict[str, Any]) -> None:
    stamp = result["evaluated_at_real"].replace(":", "-")
    path = run_dir / "gates" / "A" / f"{stamp}_{uuid4().hex}.json"
    write_json_immutable(path, result)


def latest_gate_a_report(run_dir: Path) -> dict[str, Any] | None:
    paths = list((run_dir / "gates" / "A").glob("*.json"))
    if paths:
        reports = [read_json(p) for p in paths]
        reports.sort(key=lambda r: r.get("evaluated_at_real", ""))
        return reports[-1]
    legacy = run_dir / "gates" / "gate_A.json"
    return read_json(legacy) if legacy.is_file() else None


def evaluate_gate_a(repo_root: Path, run_id: str) -> dict[str, Any]:
    """Evaluate readiness using persisted evidence; returns non-PASS rather than masking blockers."""

    run_dir = get_run_dir(repo_root, run_id)
    manifest = load_run_manifest(repo_root, run_id)
    input_lock_path = run_dir / "inputs" / "input_lock.json"
    checks: list[dict[str, str]] = []
    if not input_lock_path.is_file():
        checks.append(_check("A-001", "NOT_RUN", "Inventory input_lock.json is absent", "inputs/input_lock.json"))
        semantic = {"gate": "A", "run_id": run_id, "status": "NOT_RUN", "checks": checks}
        result = {**semantic, "evaluated_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}
        _persist_evaluation(run_dir, result)
        return result

    input_lock = read_json(input_lock_path)
    stage_report_path = run_dir / "reports" / "stage_4_3_reconciliation.json"
    stage_status = read_json(stage_report_path).get("status") if stage_report_path.is_file() else "NOT_RUN"
    checks.append(
        _check(
            "A-001",
            "PASS" if stage_status == "PASS" else "FAIL" if stage_status == "FAIL" else "BLOCKED",
            f"Stage 4.3 reconciliation={stage_status}",
            "reports/stage_4_3_reconciliation.json",
        )
    )

    table_rows: dict[str, list[dict[str, Any]]] = {}
    table_errors: list[str] = []
    for table_name in REQUIRED_TABLES:
        path = run_dir / "tables" / f"{table_name}.parquet"
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        try:
            verify_parquet_artifact(path, table_name)
            table = pq.read_table(path)
            if table.schema.names != TABLE_SCHEMAS[table_name].names:
                raise ValueError("schema field names do not match contract")
            if not manifest_path.is_file():
                raise ValueError("immutable Parquet manifest is absent")
            table_rows[table_name] = table.to_pylist()
        except Exception as exc:  # noqa: BLE001 - a gate must report every unreadable artifact as FAIL.
            table_errors.append(f"{table_name}: {type(exc).__name__}: {exc}")
    checks.append(
        _check(
            "A-002",
            "PASS" if not table_errors else "FAIL",
            "all required Ticket A tables are readable and match the contract" if not table_errors else "; ".join(table_errors),
            "tables/",
        )
    )

    raw_rows = table_rows.get("raw_inventory", [])
    read_errors = [row for row in raw_rows if row.get("read_status") != "OK"]
    filename_mismatches = [row for row in raw_rows if row.get("filename_hash_status") == "MISMATCH"]
    checks.append(
        _check(
            "A-003",
            "FAIL" if read_errors or filename_mismatches else "PASS",
            f"read_errors={len(read_errors)}; filename_hash_mismatches={len(filename_mismatches)}",
            "tables/raw_inventory.parquet",
        )
    )

    retrieval_rows = table_rows.get("retrievals", [])
    try:
        validate_retrieval_rows(retrieval_rows)
        duplicate_ids = len({row["retrieval_id"] for row in retrieval_rows}) != len(retrieval_rows)
        checks.append(
            _check(
                "A-004",
                "FAIL" if duplicate_ids else "PASS",
                f"retrieval_records={len(retrieval_rows)}; unique_retrieval_ids={len({row['retrieval_id'] for row in retrieval_rows})}",
                "tables/retrievals.parquet",
            )
        )
    except Exception as exc:  # noqa: BLE001 - a gate must report every contract failure as FAIL.
        checks.append(_check("A-004", "FAIL", f"retrieval contract violation: {exc}", "tables/retrievals.parquet"))

    strict_raw_paths = sum(bool(row.get("strict_input_eligible")) for row in raw_rows)
    unresolved_raw_paths = sum(row.get("source_provenance_status") == "UNRESOLVED_NO_ACQUISITION_EVIDENCE" for row in raw_rows)
    checks.append(
        _check(
            "A-005",
            "BLOCKED" if raw_input_blockers(raw_rows, table_rows.get("missing_coverage_ledger", [])) else "PASS",
            f"strict_raw_paths={strict_raw_paths}; unresolved_raw_paths={unresolved_raw_paths}",
            "tables/raw_inventory.parquet",
        )
    )

    source_lock = inspect_source_lock(repo_root)
    checks.append(
        _check(
            "A-006",
            "PASS" if source_lock.get("status") == "PASS" else "BLOCKED",
            source_lock.get("reason") or "source lock satisfied",
            "inputs/input_lock.json",
        )
    )
    bundle_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    bundle = read_yaml(bundle_path) if bundle_path.is_file() else {}
    current_approval = inspect_config_approval(repo_root, config_fingerprints(repo_root))
    approval_matches = current_approval["status"] == "FROZEN" and all(bundle.get(key) == value for key, value in current_approval.items())
    checks.append(
        _check(
            "A-007",
            "PASS" if approval_matches else "BLOCKED",
            f"config bundle status={bundle.get('status', 'MISSING')}",
            "inputs/proposed_config_bundle.yaml",
        )
    )
    near_policy_rows = table_rows.get("near_duplicate_candidates", [])
    near_policy_blocked = any(row.get("policy_status") == "BLOCKED_UNFROZEN_SEMANTIC_POLICY" for row in near_policy_rows)
    checks.append(
        _check(
            "A-008",
            "BLOCKED" if near_policy_blocked else "PASS",
            "near-duplicate/copy/lineage policy remains unfrozen" if near_policy_blocked else "near-duplicate policy is versioned",
            "tables/near_duplicate_candidates.parquet",
        )
    )
    safety_scope = manifest.get("safety_scope", {})
    raw_roots = manifest.get("raw_input_roots", [])
    legacy_safe = safety_scope.get("legacy_decision_inputs") == "EXCLUDED" and raw_roots == ["data/raw/stage_4_4"]
    checks.append(
        _check(
            "A-009",
            "PASS" if legacy_safe else "FAIL",
            "new run consumes the declared raw root only; legacy decision artifacts are excluded" if legacy_safe else "run manifest safety scope is not intact",
            "run_manifest.yaml",
        )
    )
    lock_status = input_lock.get("status")
    checks.append(
        _check(
            "A-010",
            "PASS" if lock_status == "READY" else "BLOCKED",
            f"input lock status={lock_status}",
            "inputs/input_lock.json",
        )
    )

    fk_errors = []
    for child_table, fks in FOREIGN_KEYS.items():
        if child_table not in table_rows:
            continue
        for child_col, (parent_table, parent_col) in fks.items():
            if parent_table not in table_rows:
                fk_errors.append(f"Missing parent table {parent_table} required by {child_table}.{child_col}")
                continue
            parent_keys = {row.get(parent_col) for row in table_rows[parent_table] if row.get(parent_col) is not None}
            for index, row in enumerate(table_rows[child_table]):
                val = row.get(child_col)
                if val is not None and val not in parent_keys:
                    fk_errors.append(f"{child_table}[{index}].{child_col}='{val}' not found in {parent_table}.{parent_col}")

    checks.append(
        _check(
            "A-011",
            "PASS" if not fk_errors else "FAIL",
            "all foreign keys resolve" if not fk_errors else f"{len(fk_errors)} FK violations; first: {fk_errors[0]}",
            "tables/",
        )
    )

    statuses = {check["status"] for check in checks}
    status = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "NOT_RUN" if "NOT_RUN" in statuses else "PASS"
    semantic = {
        "gate": "A",
        "run_id": run_id,
        "status": status,
        "checks": checks,
        "input_lock_semantic_sha256": input_lock.get("semantic_sha256"),
        "run_manifest_semantic_sha256": manifest.get("semantic_sha256"),
        "commands": [
            f"python -m kg_pipeline inventory --run {run_id} --verify-inputs",
            f"python -m kg_pipeline verify --run {run_id} --gate A",
        ],
    }
    result = {**semantic, "evaluated_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}
    _persist_evaluation(run_dir, result)
    return result


def latest_gate_g2_report(run_dir: Path) -> dict[str, Any] | None:
    paths = list((run_dir / "gates" / "G2").glob("*.json"))
    if paths:
        reports = [read_json(p) for p in paths]
        reports.sort(key=lambda r: r.get("evaluated_at_real", ""))
        return reports[-1]
    legacy = run_dir / "gates" / "gate_G2.json"
    return read_json(legacy) if legacy.is_file() else None


def evaluate_gate_g2(repo_root: Path, run_id: str) -> dict[str, Any]:
    """Evaluate M1 data/KG gate G2: fails or blocks if evaluated_count == 0,

    validates evidence span cryptographic integrity, temporal separation,
    point-in-time entity resolution, strict conservation accounting, and snapshot manifest parity.
    """
    run_dir = get_run_dir(repo_root, run_id)
    checks: list[dict[str, str]] = []

    # Read M1 pipeline tables if present
    claims_path = run_dir / "tables" / "extracted_claims.parquet"
    facts_path = run_dir / "tables" / "fact_versions.parquet"
    decisions_path = run_dir / "tables" / "adjudication_decisions.parquet"
    edges_path = run_dir / "tables" / "snapshot_edges.parquet"
    snapshots_dir = run_dir / "snapshots"

    claims_rows: list[dict[str, Any]] = []
    if claims_path.is_file():
        try:
            claims_rows = pq.read_table(claims_path).to_pylist()
        except Exception:
            claims_rows = []

    facts_rows: list[dict[str, Any]] = []
    if facts_path.is_file():
        try:
            facts_rows = pq.read_table(facts_path).to_pylist()
        except Exception:
            facts_rows = []

    decisions_rows: list[dict[str, Any]] = []
    if decisions_path.is_file():
        try:
            decisions_rows = pq.read_table(decisions_path).to_pylist()
        except Exception:
            decisions_rows = []

    edges_rows: list[dict[str, Any]] = []
    if edges_path.is_file():
        try:
            edges_rows = pq.read_table(edges_path).to_pylist()
        except Exception:
            edges_rows = []

    # G2-001: Evaluated count check (must fail/block if evaluated_count == 0)
    evaluated_count = len(claims_rows) + len(facts_rows) + len(edges_rows)
    if evaluated_count == 0:
        checks.append(
            _check(
                "G2-001",
                "FAIL",
                f"evaluated_count == 0 (claims={len(claims_rows)}, facts={len(facts_rows)}, edges={len(edges_rows)}); G2 requires evaluated_count > 0",
                "tables/",
            )
        )
    else:
        checks.append(
            _check(
                "G2-001",
                "PASS",
                f"evaluated_count={evaluated_count} (claims={len(claims_rows)}, facts={len(facts_rows)}, edges={len(edges_rows)})",
                "tables/",
            )
        )

    # G2-002: Evidence Span & Hash Cryptographic Integrity
    span_errors: list[str] = []
    bv_text_cache: dict[str, str] = {}
    bv_path = run_dir / "tables" / "body_variants.parquet"
    if bv_path.is_file():
        try:
            bv_table = pq.read_table(bv_path).to_pylist()
            for b_row in bv_table:
                b_id = b_row.get("body_variant_id")
                rel_p = b_row.get("body_blob_relative_path")
                if b_id and rel_p:
                    full_p = run_dir / rel_p
                    if full_p.is_file():
                        bv_text_cache[b_id] = full_p.read_text(encoding="utf-8")
        except Exception:
            pass

    for c in claims_rows:
        cid = c.get("claim_id")
        b_id = c.get("body_variant_id")
        start = c.get("evidence_span_start")
        end = c.get("evidence_span_end")
        h = c.get("evidence_text_hash")
        if h in ("placeholder", "placeholder_hash", "") or h is None:
            span_errors.append(f"Claim {cid} has placeholder/empty evidence_text_hash: {h}")
            continue
        if start is None or end is None or start >= end:
            span_errors.append(f"Claim {cid} has invalid span [{start}, {end})")
            continue
        if b_id in bv_text_cache:
            text = bv_text_cache[b_id]
            if end > len(text) or start < 0:
                span_errors.append(f"Claim {cid} span [{start}, {end}) exceeds text length {len(text)}")
            else:
                expected_hash = sha256_text(text[start:end])
                if h != expected_hash:
                    span_errors.append(f"Claim {cid} hash mismatch: expected {expected_hash}, got {h}")
        else:
            span_errors.append(f"Claim {cid} referenced body_variant {b_id} text blob not found in text cache")

    checks.append(
        _check(
            "G2-002",
            "FAIL" if span_errors else "PASS",
            f"verified {len(claims_rows)} evidence spans; errors={len(span_errors)}" if not span_errors else f"span verification failed: {span_errors[:3]}",
            "tables/extracted_claims.parquet",
        )
    )

    # G2-003: Temporal Decoupling & Invariant Verification
    temp_errors: list[str] = []
    for f in facts_rows:
        fid = f.get("fact_version_id")
        obs_str = f.get("evidence_observed_at")
        ing_str = f.get("ingested_at_real")
        if not obs_str:
            temp_errors.append(f"Fact {fid} missing evidence_observed_at")
        if not ing_str:
            temp_errors.append(f"Fact {fid} missing ingested_at_real")
        vf = f.get("valid_from")
        vt = f.get("valid_to")
        if vf and vt and vf >= vt:
            temp_errors.append(f"Fact {fid} valid_from {vf} >= valid_to {vt}")

    checks.append(
        _check(
            "G2-003",
            "FAIL" if temp_errors else "PASS",
            f"verified temporal integrity of {len(facts_rows)} facts" if not temp_errors else f"temporal violations: {temp_errors[:3]}",
            "tables/fact_versions.parquet",
        )
    )

    # G2-004: Point-in-Time Entity Resolution & No Future Mapping Leakage
    future_errors: list[str] = []
    if snapshots_dir.is_dir():
        for snap_dir in sorted(snapshots_dir.iterdir()):
            if not snap_dir.is_dir():
                continue
            manifest_p = snap_dir / "snapshot_manifest.yaml"
            if not manifest_p.is_file():
                manifest_p = snap_dir / "snapshot_manifest.json"
            if not manifest_p.is_file():
                continue
            try:
                m_data = read_yaml(manifest_p) if manifest_p.suffix in (".yaml", ".yml") else read_json(manifest_p)
                cutoff_raw = m_data.get("cutoff")
                if not cutoff_raw:
                    continue
                if isinstance(cutoff_raw, datetime):
                    cutoff_dt = cutoff_raw if cutoff_raw.tzinfo else cutoff_raw.replace(tzinfo=timezone.utc)
                else:
                    cutoff_dt = datetime.fromisoformat(str(cutoff_raw).replace("Z", "+00:00"))
                # Check edges against support
                supp_p = snap_dir / "snapshot_edge_support.parquet"
                if supp_p.is_file():
                    supp_rows = pq.read_table(supp_p).to_pylist()
                    fact_by_id = {row["fact_version_id"]: row for row in facts_rows if row.get("fact_version_id")}
                    for s in supp_rows:
                        f_vid = s.get("fact_version_id")
                        f_match = fact_by_id.get(f_vid)
                        if f_match:
                            f_obs = f_match.get("evidence_observed_at")
                            if f_obs:
                                f_obs_dt = f_obs if isinstance(f_obs, datetime) else datetime.fromisoformat(str(f_obs).replace("Z", "+00:00"))
                                if f_obs_dt.tzinfo is None:
                                    f_obs_dt = f_obs_dt.replace(tzinfo=timezone.utc)
                                if f_obs_dt > cutoff_dt:
                                    future_errors.append(f"Snapshot {snap_dir.name} has fact {f_vid} with obs {f_obs} > cutoff {cutoff_dt.isoformat()}")

                # Check point-in-time entity resolution: no future entity mappings in snapshot
                ent_path = run_dir / "tables" / "entity_mappings.parquet"
                if not ent_path.is_file():
                    try:
                        ent_path = resolve_run_table_path(repo_root, run_id, "entity_mappings")
                    except Exception:
                        pass
                if ent_path.is_file():
                    ent_rows = pq.read_table(ent_path).to_pylist()
                    future_mappings: dict[str, str] = {}
                    for erow in ent_rows:
                        m_avail = erow.get("mapping_available_at")
                        if m_avail:
                            m_dt = m_avail if isinstance(m_avail, datetime) else datetime.fromisoformat(str(m_avail).replace("Z", "+00:00"))
                            if m_dt.tzinfo is None:
                                m_dt = m_dt.replace(tzinfo=timezone.utc)
                            if m_dt > cutoff_dt:
                                future_mappings[erow.get("canonical_entity_id")] = erow.get("mention")

                    edges_p = snap_dir / "snapshot_edges.parquet"
                    if edges_p.is_file() and future_mappings:
                        e_rows = pq.read_table(edges_p).to_pylist()
                        for er in e_rows:
                            sub = er.get("subject_id")
                            obj = er.get("object_id")
                            for ent_id in (sub, obj):
                                if ent_id in future_mappings and ent_id != future_mappings[ent_id]:
                                    future_errors.append(
                                        f"Snapshot {snap_dir.name} has future mapped entity {ent_id} "
                                        f"(mapping available after cutoff {cutoff_dt.isoformat()})"
                                    )
            except Exception as e:
                future_errors.append(f"Error checking snapshot {snap_dir.name}: {e}")

    checks.append(
        _check(
            "G2-004",
            "FAIL" if future_errors else "PASS",
            "no future evidence or entity mappings in snapshots" if not future_errors else f"future leakage: {future_errors[:3]}",
            "snapshots/",
        )
    )

    # G2-005: Strict Conservation Accounting
    conservation_errors: list[str] = []
    if len(claims_rows) > 0:
        claimed_ids = {c["claim_id"] for c in claims_rows if c.get("claim_id")}
        decision_claim_ids = {d["claim_id"] for d in decisions_rows if d.get("claim_id")}
        missing_decisions = claimed_ids - decision_claim_ids
        if missing_decisions:
            conservation_errors.append(f"Claims missing explicit adjudication decisions: {len(missing_decisions)}")

    checks.append(
        _check(
            "G2-005",
            "FAIL" if conservation_errors else "PASS",
            f"strict conservation holds: {len(claims_rows)} claims all have explicit decisions" if not conservation_errors else f"conservation mismatch: {conservation_errors}",
            "tables/adjudication_decisions.parquet",
        )
    )

    # G2-006: Snapshot Manifest & Hash Parity Check
    manifest_errors: list[str] = []
    if not snapshots_dir.is_dir() or not any(snapshots_dir.iterdir()):
        manifest_errors.append("No snapshots generated in snapshots/")
    else:
        for snap_dir in sorted(snapshots_dir.iterdir()):
            if not snap_dir.is_dir():
                continue
            m_yaml = snap_dir / "snapshot_manifest.yaml"
            if not m_yaml.is_file():
                manifest_errors.append(f"Missing snapshot_manifest.yaml in {snap_dir.name}")
                continue
            try:
                m_data = read_yaml(m_yaml)
                exp_graph_hash = m_data.get("graph_semantic_hash")
                exp_manifest_hash = m_data.get("snapshot_manifest_hash")
                semantic = {
                    k: (v.isoformat() if isinstance(v, (datetime, date)) else v)
                    for k, v in m_data.items()
                    if k not in ("created_at_real", "snapshot_manifest_hash")
                }
                computed_m_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True, default=str).encode("utf-8")).hexdigest()
                if exp_manifest_hash != computed_m_hash:
                    manifest_errors.append(f"Manifest hash mismatch in {snap_dir.name}")
                edges_p = snap_dir / "snapshot_edges.parquet"
                if not edges_p.is_file():
                    manifest_errors.append(f"Missing snapshot_edges.parquet in {snap_dir.name}")
                else:
                    e_table = pq.read_table(edges_p).to_pylist()
                    sorted_triples = sorted((r["subject_id"], r["relation_id"], r["object_id"]) for r in e_table)
                    hasher = hashlib.sha256()
                    for s, r, o in sorted_triples:
                        hasher.update(f"{s}\t{r}\t{o}\n".encode("utf-8"))
                    computed_graph_hash = hasher.hexdigest()
                    if exp_graph_hash != computed_graph_hash:
                        manifest_errors.append(f"Graph hash mismatch in {snap_dir.name}: {exp_graph_hash} vs {computed_graph_hash}")
            except Exception as e:
                manifest_errors.append(f"Failed verifying snapshot {snap_dir.name}: {e}")

    checks.append(
        _check(
            "G2-006",
            "FAIL" if manifest_errors else "PASS",
            "all snapshot manifests exist and match graph semantic hashes" if not manifest_errors else f"snapshot manifest parity errors: {manifest_errors[:3]}",
            "snapshots/",
        )
    )

    statuses = {check["status"] for check in checks}
    status = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "NOT_RUN" if "NOT_RUN" in statuses else "PASS"

    semantic = {
        "gate": "G2",
        "run_id": run_id,
        "status": status,
        "checks": checks,
        "evaluated_count": evaluated_count,
        "claims_count": len(claims_rows),
        "facts_count": len(facts_rows),
        "edges_count": len(edges_rows),
        "commands": [
            f"python scripts/verify_g2.py --run {run_id}",
        ],
    }
    result = {**semantic, "evaluated_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}

    stamp = result["evaluated_at_real"].replace(":", "-")
    path = run_dir / "gates" / "G2" / f"{stamp}_{uuid4().hex}.json"
    write_json_immutable(path, result)
    return result
