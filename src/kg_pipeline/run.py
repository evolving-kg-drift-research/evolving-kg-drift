"""New-run creation and immutable input/config lock inspection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .baseline import inspect_config_approval, inspect_source_lock
from .contracts import CONTRACT_VERSION
from .contract_authority import load_machine_contract
from .hashing import repo_relative, sha256_file, sha256_json, utc_now_iso
from .storage import ArtifactConflict, read_yaml, verify_parquet_artifact, write_yaml_immutable

ARTIFACT_REF_VERSION = "m1_artifact_ref_v1"

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
    "config/entity_catalog.yaml",
    "config/llm_adapter.yaml",
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


def machine_schema_identity(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config" / "schema.yaml"
    if not path.is_file():
        return {"status": "MISSING", "schema_version": None, "physical_sha256": None}
    document = load_machine_contract(repo_root)
    return {
        "status": "PRESENT",
        "schema_version": document["schema_version"],
        "physical_sha256": sha256_file(path),
    }


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

    adapter_path = repo_root / "config" / "llm_adapter.yaml"
    if adapter_path.is_file():
        adapter_config = read_yaml(adapter_path)
        if not isinstance(adapter_config, dict):
            raise ArtifactConflict("config/llm_adapter.yaml must contain a YAML mapping")
        resolved_config["llm_adapter"] = adapter_config
    else:
        # Keep the field explicit in the proposed bundle without inventing a
        # runnable adapter; extraction rejects a missing declaration.
        resolved_config["llm_adapter"] = None

    semantic = {
        "bundle_version": "ticket_a_proposed_baseline_v4",
        "machine_schema": machine_schema_identity(repo_root),
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
    scientific_locked: bool = False,
) -> dict[str, Any]:
    valid_modes = ("inventory", "extraction", "adjudication", "snapshot", "kge", "drift")
    if mode not in valid_modes:
        raise ValueError(f"Ticket A supports only valid run modes {valid_modes} (got {mode})")
    if type(scientific_locked) is not bool:
        raise ValueError("scientific_locked must be a boolean")
    candidates = config_fingerprints(repo_root)
    approval = inspect_config_approval(repo_root, candidates)
    if scientific_locked and approval.get("status") != "FROZEN":
        raise ArtifactConflict(
            "Scientific locked run cannot be initialized from a draft or unapproved configuration baseline"
        )
    if scientific_locked:
        from .locked_mode import validate_dependency_lock

        try:
            validate_dependency_lock(
                repo_root / "pyproject.toml",
                repo_root / "requirements.lock.txt",
            )
        except ValueError as exc:
            raise ArtifactConflict(
                "Scientific locked run requires every direct dependency to be exactly pinned in requirements.lock.txt"
            ) from exc
    bundle = _bundle_payload(repo_root)
    bundle["scientific_locked"] = scientific_locked
    if scientific_locked and mode == "extraction":
        from .locked_mode import validate_local_adapter_declaration

        try:
            validate_local_adapter_declaration(bundle["resolved_config"].get("llm_adapter"))
        except ValueError as exc:
            raise ArtifactConflict(
                "Scientific locked extraction requires a pinned local adapter in the approved "
                "config/llm_adapter.yaml"
            ) from exc
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
        "scientific_locked": scientific_locked,
        "pipeline_contract_version": "ticket_a_v1",
        "machine_schema": machine_schema_identity(repo_root),
        "raw_input_roots": ["data/raw/stage_4_4"],
        "upstream_stage_4_3_run": "data/stage_4_3_runs/stage4_3_final_20260906T144016Z",
        "code_fingerprint_sha256": package_fingerprint(repo_root),
        "config_candidates": candidates,
        "config_approval": approval,
        "source_lock_status_at_init": source_lock["status"],
        "input_lock_path": "inputs/input_lock.json",
        "safety_scope": safety_scope,
    }
    if parent_run_id:
        semantic["parent_run_id"] = parent_run_id

    manifest_path = run_dir / "run_manifest.yaml"
    semantic["config_bundle_semantic_sha256"] = sha256_json(bundle)
    manifest = {
        **semantic,
        "created_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(semantic),
    }
    if manifest_path.is_file():
        existing_manifest = load_run_manifest(repo_root, run_id)
        if existing_manifest.get("run_id") != run_id or existing_manifest.get("mode") != mode:
            raise ArtifactConflict(f"Existing run manifest has incompatible identity: {manifest_path}")
        if existing_manifest.get("scientific_locked", False) is not scientific_locked:
            raise ArtifactConflict("Existing run scientific_locked mode cannot be changed in place")
        manifest_result = {
            "status": "REUSED",
            "semantic_sha256": existing_manifest.get("semantic_sha256"),
        }
    else:
        manifest_result = write_yaml_immutable(manifest_path, manifest)
    bundle_result = write_yaml_immutable(run_dir / "inputs" / "proposed_config_bundle.yaml", bundle)
    return {
        "run_dir": str(run_dir),
        "manifest": manifest_result,
        "proposed_bundle": bundle_result,
        "source_lock_status": source_lock["status"],
    }


def load_run_manifest(repo_root: Path, run_id: str, *, check_workspace: bool = True) -> dict[str, Any]:
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
    bundle_path = path.parent / "inputs" / "proposed_config_bundle.yaml"
    if not bundle_path.is_file():
        raise ArtifactConflict("Run is missing its immutable resolved config bundle")
    bundle = read_yaml(bundle_path)
    if not isinstance(bundle, dict) or manifest.get("config_bundle_semantic_sha256") != sha256_json(bundle):
        raise ArtifactConflict("Run resolved config bundle semantic hash mismatch")
    if check_workspace and manifest.get("code_fingerprint_sha256") != package_fingerprint(repo_root):
        raise ArtifactConflict("Executing code differs from the initialized run; create a new run")
    if check_workspace and manifest.get("config_candidates") != config_fingerprints(repo_root):
        raise ArtifactConflict("Configuration differs from the initialized run; create a new run")
    if check_workspace and manifest.get("config_approval") != inspect_config_approval(repo_root, config_fingerprints(repo_root)):
        raise ArtifactConflict("Configuration approval differs from the initialized run; create a new run")
    return manifest


def verified_run_ancestry(repo_root: Path, run_id: str, *, check_workspace: bool = True) -> set[str]:
    """Return the declared run lineage after checking each manifest and cycles."""
    lineage: set[str] = set()
    current: str | None = run_id
    while current:
        if current in lineage:
            raise ArtifactConflict(f"Parent-run lineage cycle at {current}")
        lineage.add(current)
        manifest = load_run_manifest(
            repo_root, current, check_workspace=check_workspace and current == run_id
        )
        current = manifest.get("parent_run_id")
    return lineage


def _artifact_location(repo_root: Path, path: Path) -> tuple[str, str]:
    runs_root = (repo_root / "runs").resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(runs_root)
    except ValueError as exc:
        raise ArtifactConflict(f"Artifact is outside runs/: {path}") from exc
    if len(relative.parts) < 3:
        raise ArtifactConflict(f"Artifact path lacks run-relative location: {path}")
    producer_run = validate_run_id(relative.parts[0])
    return producer_run, Path(*relative.parts[1:]).as_posix()


def _parquet_ref(repo_root: Path, path: Path, table_name: str, stage_name: str) -> dict[str, Any]:
    producer_run, relative = _artifact_location(repo_root, path)
    sidecar = verify_parquet_artifact(path, table_name)
    return {
        "ref_version": ARTIFACT_REF_VERSION,
        "producer_run_id": producer_run,
        "producer_stage": stage_name,
        "path": relative,
        "table_name": table_name,
        "contract_version": sidecar["contract_version"],
        "physical_sha256": sidecar["physical_sha256_computed_at_real"],
        "semantic_sha256": sidecar["semantic_sha256"],
        "row_count": sidecar["row_count"],
    }


def _verify_ref(repo_root: Path, ref: dict[str, Any]) -> Path:
    if ref.get("ref_version") != ARTIFACT_REF_VERSION:
        raise ArtifactConflict("Unsupported or missing ArtifactRef version")
    run_dir = get_run_dir(repo_root, ref["producer_run_id"])
    relative = Path(ref["path"])
    path = (run_dir / relative).resolve()
    if relative.is_absolute() or run_dir not in path.parents:
        raise ArtifactConflict("ArtifactRef path escapes producer run")
    actual = _parquet_ref(repo_root, path, ref["table_name"], ref["producer_stage"])
    for key, value in actual.items():
        if ref.get(key) != value:
            raise ArtifactConflict(f"ArtifactRef {key} mismatch: {path}")
    return path


def verify_stage_manifest(
    repo_root: Path, run_id: str, stage_name: str, *,
    _active: set[tuple[str, str]] | None = None,
    _verified: dict[tuple[str, str], dict[str, Any]] | None = None,
    check_workspace: bool = True,
) -> dict[str, Any]:
    """Verify a completed producer and every bound ancestor, detecting lineage cycles."""
    key = (run_id, stage_name)
    active = _active if _active is not None else set()
    verified = _verified if _verified is not None else {}
    if key in active:
        raise ArtifactConflict(f"Stage lineage cycle at {run_id}/{stage_name}")
    if key in verified:
        return verified[key]
    active.add(key)
    try:
        ancestry = verified_run_ancestry(repo_root, run_id, check_workspace=check_workspace)
        run_manifest = load_run_manifest(repo_root, run_id, check_workspace=False)
        path = get_run_dir(repo_root, run_id) / "reports" / f"{stage_name}_manifest.yaml"
        if not path.is_file():
            raise ArtifactConflict(f"Missing producer stage manifest: {path}")
        manifest = read_yaml(path)
        if not isinstance(manifest, dict):
            raise ArtifactConflict(f"Invalid producer stage manifest: {path}")
        semantic = {k: v for k, v in manifest.items() if k not in {"created_at_real", "stage_manifest_hash"}}
        if manifest.get("stage_manifest_hash") != sha256_json(semantic):
            raise ArtifactConflict(f"Producer stage manifest hash mismatch: {path}")
        if manifest.get("run_id") != run_id or manifest.get("stage_name") != stage_name:
            raise ArtifactConflict(f"Producer stage identity mismatch: {path}")
        if manifest.get("status") != "COMPLETED":
            raise ArtifactConflict(f"Producer stage is not COMPLETED: {path}")
        if manifest.get("code_fingerprint_sha256") != run_manifest.get("code_fingerprint_sha256"):
            raise ArtifactConflict(f"Producer stage code binding mismatch: {path}")
        if not manifest.get("output_artifacts"):
            raise ArtifactConflict(f"Producer stage has no bound outputs: {path}")
        if "gate_a_ref" in manifest:
            from .gates import require_gate_a
            if manifest["gate_a_ref"] != require_gate_a(repo_root, run_id, check_workspace=check_workspace):
                raise ArtifactConflict(f"Stage Gate A binding mismatch: {path}")
        for ref in manifest["output_artifacts"]:
            if ref.get("producer_run_id") != run_id or ref.get("producer_stage") != stage_name:
                raise ArtifactConflict(f"Producer output identity mismatch: {path}")
            _verify_ref(repo_root, ref)
        for ref in manifest.get("input_artifacts", []):
            if ref.get("producer_run_id") not in ancestry:
                raise ArtifactConflict(f"Input producer is outside run ancestry: {path}")
            parent = verify_stage_manifest(
                repo_root, ref["producer_run_id"], ref["producer_stage"],
                _active=active, _verified=verified,
                check_workspace=check_workspace and ref["producer_run_id"] == run_id,
            )
            if ref.get("producer_stage_manifest_hash") != parent["stage_manifest_hash"]:
                raise ArtifactConflict(f"Input producer manifest binding mismatch: {path}")
            if not any(
                all(out.get(k) == ref.get(k) for k in out)
                for out in parent["output_artifacts"]
            ):
                raise ArtifactConflict(f"Input is not a declared producer output: {path}")
            _verify_ref(repo_root, ref)
        verified[key] = manifest
        return manifest
    finally:
        active.remove(key)


def _producer_ref_for_table(repo_root: Path, path: Path, table_name: str) -> dict[str, Any]:
    producer_run, relative = _artifact_location(repo_root, path)
    reports = get_run_dir(repo_root, producer_run) / "reports"
    for manifest_path in sorted(reports.glob("*_manifest.yaml")):
        candidate = read_yaml(manifest_path)
        if not isinstance(candidate, dict) or "stage_manifest_hash" not in candidate:
            continue
        if not any(
            isinstance(ref, dict) and ref.get("path") == relative and ref.get("table_name") == table_name
            for ref in candidate.get("output_artifacts", [])
        ):
            continue
        stage_name = manifest_path.name.removesuffix("_manifest.yaml")
        manifest = verify_stage_manifest(repo_root, producer_run, stage_name, check_workspace=False)
        for ref in manifest["output_artifacts"]:
            if ref.get("path") == relative and ref.get("table_name") == table_name:
                return {**ref, "producer_stage_manifest_hash": manifest["stage_manifest_hash"]}
    raise ArtifactConflict(f"No COMPLETED producer binds {path}")


def resolve_run_table_path(repo_root: Path, run_id: str, table_name: str) -> Path:
    """Resolve only a table with an intact sidecar and completed producer lineage."""
    verified_run_ancestry(repo_root, run_id)
    curr_id: str | None = run_id
    visited: set[str] = set()
    while curr_id:
        if curr_id in visited:
            raise ArtifactConflict(f"Parent-run lineage cycle at {curr_id}")
        visited.add(curr_id)
        run_dir = get_run_dir(repo_root, curr_id)
        candidate = run_dir / "tables" / f"{table_name}.parquet"
        manifest = load_run_manifest(repo_root, curr_id, check_workspace=False)
        if candidate.is_file():
            _producer_ref_for_table(repo_root, candidate, table_name)
            return candidate
        curr_id = manifest.get("parent_run_id")
    raise FileNotFoundError(f"No completed producer for table {table_name} in run {run_id} ancestry")


def create_stage_manifest(
    repo_root: Path,
    run_id: str,
    stage_name: str,
    *,
    input_artifacts: list[dict[str, Any]] | None = None,
    output_artifacts: list[dict[str, Any]] | None = None,
    conservation_metrics: dict[str, Any] | None = None,
    status: str = "COMPLETED",
    parent_run_id: str | None = None,
    gate_a_ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Publish a completed stage only after binding verified inputs and outputs."""
    import subprocess

    if status != "COMPLETED":
        raise ArtifactConflict("Only completed stages may publish output ArtifactRefs")
    run_manifest = load_run_manifest(repo_root, run_id)
    verified_run_ancestry(repo_root, run_id)
    run_dir = get_run_dir(repo_root, run_id)
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    git_commit = "unknown"
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        git_commit = proc.stdout.strip()
    except Exception:
        pass

    inputs = []
    for item in input_artifacts or []:
        inputs.append(_producer_ref_for_table(repo_root, Path(item["path"]), item["table"]))
    outputs = []
    for item in output_artifacts or []:
        path = Path(item["path"])
        producer_run, _ = _artifact_location(repo_root, path)
        if producer_run != run_id:
            raise ArtifactConflict("Stage output belongs to another run")
        ref = _parquet_ref(repo_root, path, item["table"], stage_name)
        if "count" in item and item["count"] != ref["row_count"]:
            raise ArtifactConflict(f"Stage output count mismatch: {path}")
        outputs.append(ref)
    if not outputs:
        raise ArtifactConflict("Completed stage must bind at least one output")
    semantic: dict[str, Any] = {
        "stage_name": stage_name,
        "run_id": run_id,
        "status": status,
        "contract_version": CONTRACT_VERSION,
        "code_fingerprint_sha256": run_manifest["code_fingerprint_sha256"],
        "git_commit": git_commit,
        "input_artifacts": inputs,
        "output_artifacts": outputs,
        "conservation_metrics": conservation_metrics or {},
    }
    if gate_a_ref is not None:
        from .gates import require_gate_a
        if gate_a_ref != require_gate_a(repo_root, run_id):
            raise ArtifactConflict("Stage Gate A reference is not current")
        semantic["gate_a_ref"] = gate_a_ref
    if parent_run_id:
        semantic["parent_run_id"] = parent_run_id

    manifest = {
        **semantic,
        "created_at_real": utc_now_iso(),
        "stage_manifest_hash": sha256_json(semantic),
    }

    manifest_path = reports_dir / f"{stage_name}_manifest.yaml"
    if manifest_path.is_file():
        existing = verify_stage_manifest(repo_root, run_id, stage_name)
        if existing["stage_manifest_hash"] != manifest["stage_manifest_hash"]:
            raise ArtifactConflict(f"Refusing to replace completed stage manifest: {manifest_path}")
        return existing
    write_yaml_immutable(manifest_path, manifest)
    return verify_stage_manifest(repo_root, run_id, stage_name)
