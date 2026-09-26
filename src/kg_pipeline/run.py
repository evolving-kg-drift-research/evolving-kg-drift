"""New-run creation and immutable input/config lock inspection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .baseline import inspect_config_approval, inspect_source_lock
from .hashing import repo_relative, sha256_file, sha256_json, utc_now_iso
from .storage import ArtifactConflict, read_yaml, write_yaml_immutable

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,80}$")

CONFIG_CANDIDATES = (
    "config/protocol.yaml",
    "config/ontology.yaml",
    "config/schema.yaml",
    "config/sources.yaml",
    "config/corpus_scope.yaml",
    "config/filter_policy_v1.yaml",
    "config/stage_4_3.yaml",
    "config/snapshot_cutoffs.yaml",
    "requirements.lock.txt",
    "pyproject.toml",
    "configs/protocol_v1.yaml",
    "configs/data.yaml",
    "configs/kge.yaml",
    "configs/statistics.yaml",
    "data/manifests/sources.lock.json",
)


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("Run IDs must be 3-81 characters of letters, digits, _ or -, with no path separators")
    return run_id


def get_run_dir(repo_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    candidate = (repo_root / "runs" / run_id).resolve()
    runs_root = (repo_root / "runs").resolve()
    if runs_root not in (candidate, *candidate.parents):
        raise ValueError("Run path escapes the runs directory")
    return candidate


def package_fingerprint(repo_root: Path) -> str:
    src_dirs = [
        repo_root / "src" / "kg_pipeline",
        repo_root / "src" / "temporal",
        repo_root / "src" / "kge",
        repo_root / "src" / "drift",
    ]
    file_hashes: dict[str, str] = {}
    for src_dir in src_dirs:
        if src_dir.is_dir():
            for path in sorted(src_dir.rglob("*.py")):
                if path.is_file():
                    file_hashes[repo_relative(path, repo_root)] = sha256_file(path)
    return sha256_json(file_hashes)


def config_fingerprints(repo_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in CONFIG_CANDIDATES:
        path = repo_root / relative
        records.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return records


def _bundle_payload(repo_root: Path) -> dict[str, Any]:
    candidate_files = config_fingerprints(repo_root)

    resolved_config: dict[str, Any] = {}
    for p_cand in ("configs/protocol_v1.yaml", "config/protocol.yaml"):
        p_path = repo_root / p_cand
        if p_path.is_file():
            try:
                resolved_config["protocol"] = read_yaml(p_path)
            except Exception:
                resolved_config["protocol"] = {}
            break

    ont_path = repo_root / "config" / "ontology.yaml"
    if ont_path.is_file():
        try:
            resolved_config["ontology"] = read_yaml(ont_path)
        except Exception:
            resolved_config["ontology"] = {}

    src_path = repo_root / "config" / "sources.yaml"
    if src_path.is_file():
        try:
            resolved_config["sources"] = read_yaml(src_path)
        except Exception:
            resolved_config["sources"] = {}

    fp_path = repo_root / "config" / "filter_policy_v1.yaml"
    if fp_path.is_file():
        try:
            resolved_config["filter_policy"] = read_yaml(fp_path)
        except Exception:
            resolved_config["filter_policy"] = {}

    sc_path = repo_root / "config" / "snapshot_cutoffs.yaml"
    if sc_path.is_file():
        try:
            resolved_config["snapshot_cutoffs"] = read_yaml(sc_path)
        except Exception:
            resolved_config["snapshot_cutoffs"] = {}

    kge_path = repo_root / "configs" / "kge.yaml"
    if kge_path.is_file():
        try:
            resolved_config["kge"] = read_yaml(kge_path)
        except Exception:
            resolved_config["kge"] = {}

    stat_path = repo_root / "configs" / "statistics.yaml"
    if stat_path.is_file():
        try:
            resolved_config["drift"] = read_yaml(stat_path)
        except Exception:
            resolved_config["drift"] = {}

    catalog_path = repo_root / "config" / "entity_catalog.yaml"
    entity_catalog: dict[str, str] = {}
    if catalog_path.is_file():
        try:
            loaded_cat = read_yaml(catalog_path)
            if isinstance(loaded_cat, dict):
                entity_catalog = loaded_cat
        except Exception:
            entity_catalog = {}
    resolved_config["entity_catalog"] = entity_catalog

    resolved_config["llm_adapter"] = {
        "type": "mock",
        "model": "offline_mock",
        "temperature": 0.0,
    }

    semantic = {
        "bundle_version": "ticket_a_proposed_baseline_v3",
        **inspect_config_approval(repo_root, candidate_files),
        "candidate_files": candidate_files,
        "resolved_config": resolved_config,
        "entity_catalog": entity_catalog,
        "ontology_rules": resolved_config.get("ontology", {}).get("relations", {}),
        "resolved_semantic_decisions": [
            "ADR 0005: Time fields retrieved_at_real and ingested_at_real remain completely separated.",
            "ADR 0005: Ontology is frozen at 10 strictly defined active relations.",
            "ADR 0005: Exact-body CAS deduplication policy is approved and frozen for Stage A.",
            "ADR 0007: Preserve original protocol source hashes; missing originals remain blocking."
        ],
    }
    return {**semantic, "created_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}


def init_run(
    repo_root: Path,
    run_id: str,
    *,
    mode: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    valid_modes = ("inventory", "extraction", "adjudication", "snapshot", "kge", "drift")
    if mode not in valid_modes:
        raise ValueError(f"Ticket A supports only valid run modes {valid_modes} (got {mode})")
    run_dir = get_run_dir(repo_root, run_id)
    for relative in ("inputs", "tables", "body_blobs", "reports", "gates", "logs"):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)

    source_lock = inspect_source_lock(repo_root)

    if mode == "inventory":
        safety_scope = {
            "legacy_decision_inputs": "EXCLUDED",
            "raw_input_mutation": "FORBIDDEN",
            "llm_calls": "FORBIDDEN_IN_TICKET_A",
            "network_collection": "FORBIDDEN_IN_TICKET_A",
            "neo4j_writes": "FORBIDDEN_IN_TICKET_A",
        }
    elif mode == "extraction":
        safety_scope = {
            "legacy_decision_inputs": "EXCLUDED",
            "raw_input_mutation": "FORBIDDEN",
            "llm_calls": "LOCAL_OR_MOCK_ONLY",
            "network_collection": "FORBIDDEN",
            "neo4j_writes": "FORBIDDEN",
        }
    else:
        safety_scope = {
            "legacy_decision_inputs": "EXCLUDED",
            "raw_input_mutation": "FORBIDDEN",
            "llm_calls": "FORBIDDEN",
            "network_collection": "FORBIDDEN",
            "neo4j_writes": "FORBIDDEN",
        }

    semantic: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "pipeline_contract_version": "ticket_a_v1",
        "raw_input_roots": ["data/raw/stage_4_4"],
        "upstream_stage_4_3_run": "data/stage_4_3_runs/stage4_3_final_20260906T144016Z",
        "code_fingerprint_sha256": package_fingerprint(repo_root),
        "config_candidates": config_fingerprints(repo_root),
        "config_approval": inspect_config_approval(repo_root, config_fingerprints(repo_root)),
        "source_lock_status_at_init": source_lock["status"],
        "input_lock_path": "inputs/input_lock.json",
        "safety_scope": safety_scope,
    }
    if parent_run_id:
        semantic["parent_run_id"] = parent_run_id

    manifest = {
        **semantic,
        "created_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(semantic),
    }
    manifest_path = run_dir / "run_manifest.yaml"
    if manifest_path.is_file():
        existing_manifest = load_run_manifest(repo_root, run_id)
        if existing_manifest.get("run_id") != run_id or existing_manifest.get("mode") != mode:
            raise ArtifactConflict(f"Existing run manifest has incompatible identity: {manifest_path}")
        manifest_result = {
            "status": "REUSED",
            "semantic_sha256": existing_manifest.get("semantic_sha256"),
        }
    else:
        manifest_result = write_yaml_immutable(manifest_path, manifest)
    bundle_result = write_yaml_immutable(run_dir / "inputs" / "proposed_config_bundle.yaml", _bundle_payload(repo_root))
    return {
        "run_dir": str(run_dir),
        "manifest": manifest_result,
        "proposed_bundle": bundle_result,
        "source_lock_status": source_lock["status"],
    }


def load_run_manifest(repo_root: Path, run_id: str) -> dict[str, Any]:
    path = get_run_dir(repo_root, run_id) / "run_manifest.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Run has not been initialized: {path}")
    manifest = read_yaml(path)
    if not isinstance(manifest, dict):
        raise ArtifactConflict("Run manifest must be a mapping")
    semantic = {key: value for key, value in manifest.items() if key not in {"created_at_real", "semantic_sha256"}}
    if manifest.get("semantic_sha256") != sha256_json(semantic):
        raise ArtifactConflict("Run manifest semantic hash mismatch")
    if manifest.get("run_id") != run_id:
        raise ArtifactConflict("Run manifest identity mismatch")
    if manifest.get("code_fingerprint_sha256") != package_fingerprint(repo_root):
        raise ArtifactConflict("Executing code differs from the initialized run; create a new run")
    if manifest.get("config_candidates") != config_fingerprints(repo_root):
        raise ArtifactConflict("Configuration differs from the initialized run; create a new run")
    if manifest.get("config_approval") != inspect_config_approval(repo_root, config_fingerprints(repo_root)):
        raise ArtifactConflict("Configuration approval differs from the initialized run; create a new run")
    return manifest


def resolve_run_table_path(repo_root: Path, run_id: str, table_name: str) -> Path:
    """Find a table parquet path in run_id, falling back up the parent_run_id chain."""
    curr_id: str | None = run_id
    visited: set[str] = set()

    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        run_dir = get_run_dir(repo_root, curr_id)
        candidate = run_dir / "tables" / f"{table_name}.parquet"
        if candidate.is_file():
            return candidate
        manifest_path = run_dir / "run_manifest.yaml"
        if manifest_path.is_file():
            try:
                manifest = read_yaml(manifest_path)
                curr_id = manifest.get("parent_run_id") if isinstance(manifest, dict) else None
            except Exception:
                curr_id = None
        else:
            curr_id = None

    return get_run_dir(repo_root, run_id) / "tables" / f"{table_name}.parquet"
