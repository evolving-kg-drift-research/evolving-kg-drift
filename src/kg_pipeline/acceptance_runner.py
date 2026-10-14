"""One-stage acceptance controls; missing inputs/backends never auto-advance."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .acceptance_contract import PublicContract
from .baseline import inspect_source_lock
from .contract_authority import audit_machine_contract
from .hashing import sha256_file, sha256_json, utc_now_iso
from .rebuild_artifacts import RebuildBlocked, artifact_path, read_verified, require_decision
from .run import get_run_dir, load_run_manifest
from .storage import read_json, write_json_immutable


@dataclass(frozen=True)
class StageSpec:
    previous: str | None
    requirements: tuple[str, ...]
    outputs: tuple[str, ...]


STAGES = {
    "4.3": StageSpec(None, ("locked_discovery", "coverage_reconciliation"), ("reconciliation_report",)),
    "4.4": StageSpec("4.3", ("raw_inventory", "retrieval_evidence", "body_parser"), ("raw_source_versions", "body_variants")),
    "4.5": StageSpec("4.4", ("dedup_policy", "copy_origin_evidence"), ("document_clusters", "lineage_edges")),
    "4.6": StageSpec("4.5", ("filter_policy", "corpus_scope"), ("corpus_filtered", "filter_decisions")),
    "4.7": StageSpec("4.6", ("sampling_plan", "annotation_guideline", "pilot_gold", "ontology"), ("pilot_report", "ontology_freeze")),
    "4.8": StageSpec("4.7", ("mention_occurrences", "identity_policy", "mapping_reviews"), ("entity_mentions", "entity_mapping_versions")),
    "4.9": StageSpec("4.8", ("article_inventory", "extractor_config", "hosted_registration"), ("claims", "claim_evidence", "extractor_manifest")),
    "4.10": StageSpec("4.9", ("claims", "observation_proofs", "temporal_policy"), ("claims_temporal", "evidence_time_provenance")),
    "4.11": StageSpec("4.10", ("claims_temporal", "mapping_reviews", "support_reviews"), ("adjudication_decisions", "pending_conflicts")),
    "4.12": StageSpec("4.11", ("adjudication_decisions", "reviewed_fact_rows", "fact_store_policy"), ("fact_versions", "fact_version_lineage")),
    "4.13": StageSpec("4.12", ("quality_inputs", "threshold_annex", "gold"), ("quality_gate_report",)),
    "4.14": StageSpec("4.13", ("pipeline_freeze", "main_inventory", "budget_approval"), ("main_corpus_manifest",)),
    "4.15": StageSpec("4.14", ("main_fact_store", "event_policy", "qa_feasibility_policy"), ("kg_events", "feasibility_report")),
    "4.16": StageSpec("4.15", ("kg_events", "boundary_policy", "feasibility_report"), ("snapshot_boundaries", "transition_metadata")),
    "4.17": StageSpec("4.16", ("main_fact_store", "snapshot_boundaries", "mapping_history"), ("canonical_snapshots", "snapshot_manifests")),
    "4.18": StageSpec("4.17", ("canonical_snapshots", "neo4j_target"), ("parity_report", "handoff_inventory")),
}


def readiness(root: Path) -> dict[str, Any]:
    """Read-only engineering/authority inventory; never create a run or certificate."""
    source = inspect_source_lock(root)
    schema = audit_machine_contract(root)
    package_path = root / "docs/audit/m1_acceptance_design_v2/manifest.json"
    package = read_json(package_path) if package_path.is_file() else {}
    package_checks = []
    for name, expected in package.get("files_sha256", {}).items():
        path = artifact_path(package_path.parent, name)
        package_checks.append({"path": name, "status": "PASS" if path.is_file() and sha256_file(path) == expected else "FAIL"})
    candidate = package_path.parent / "schema_1_1_candidate.yaml"
    candidate_count = None
    if candidate.is_file():
        candidate_count = len(PublicContract.load(candidate).schemas)
    return {"scope": "engineering_readiness_only", "status": "BLOCKED", "sources": source,
            "runtime_schema": schema, "candidate_table_count": candidate_count,
            "candidate_hash_checks": package_checks, "candidate_activation": "NOT_APPROVED_NOT_APPLIED",
            "prerequisites": {"gold": "REQUIRED", "threshold_annex": "REQUIRED",
                              "gemini_budget": "REQUIRED", "neo4j_readback": "NOT_EXECUTED"},
            "stages": {stage: {"previous": spec.previous, "requirements": list(spec.requirements),
                               "outputs": list(spec.outputs)} for stage, spec in STAGES.items()}}


def _stage_inputs(root: Path, run_id: str, stage: str, phase: str, inputs_ref: dict[str, Any]) -> tuple[dict, dict]:
    if stage not in STAGES or phase not in {"pilot", "main"}:
        raise RebuildBlocked("An explicit single stage and phase are required")
    if stage == "4.3":
        raise RebuildBlocked("Stage 4.3 acquisition is locked; use read-only reconciliation separately")
    if stage == "4.7" and phase != "pilot":
        raise RebuildBlocked("Ontology pilot must run in pilot phase")
    if stage in {"4.14", "4.15", "4.16", "4.18"} and phase != "main":
        raise RebuildBlocked("This stage requires main phase after pilot validation")
    if inspect_source_lock(root)["status"] != "PASS":
        raise RebuildBlocked("Authoritative source originals are not verified")
    manifest = load_run_manifest(root, run_id)
    if manifest.get("scientific_locked") is not True:
        raise RebuildBlocked("Stage execution requires a frozen scientific run")
    if audit_machine_contract(root)["status"] != "PASS":
        raise RebuildBlocked("Public/runtime typed schema is not activated and compatible")
    inputs = read_verified(root, inputs_ref)
    if (inputs.get("run_id") != run_id or inputs.get("stage") != stage or inputs.get("phase") != phase
            or inputs.get("run_manifest_sha256") != manifest["semantic_sha256"]):
        raise RebuildBlocked("Stage input identity/run binding differs")
    refs = inputs.get("references")
    if not isinstance(refs, dict) or set(refs) != set(STAGES[stage].requirements):
        raise RebuildBlocked("Stage prerequisite references must match exactly")
    verified = {name: read_verified(root, ref) for name, ref in refs.items()}
    require_decision(root, inputs.get("execution_decision_id"), action="approve_stage_execution", bindings={
        "stage": stage, "phase": phase, "input_manifest_sha256": inputs_ref["sha256"],
        "run_manifest_sha256": manifest["semantic_sha256"],
    })
    previous_ref = inputs.get("previous_stage_report_ref")
    if STAGES[stage].previous is not None:
        previous = read_verified(root, previous_ref or {})
        semantic = {k: v for k, v in previous.items() if k not in {"evaluated_at_real", "semantic_sha256"}}
        if (previous.get("stage") != STAGES[stage].previous or previous.get("status") != "PASS"
                or previous.get("scope") != "artifact_backed_stage"
                or previous.get("phase") != ("pilot" if stage == "4.14" else phase)
                or previous.get("semantic_sha256") != sha256_json(semantic)):
            raise RebuildBlocked("Previous stage was not independently validated PASS")
        output_refs = previous.get("output_refs")
        if not isinstance(output_refs, list) or not output_refs:
            raise RebuildBlocked("Previous stage has no verified producer outputs")
        for ref in output_refs:
            read_verified(root, ref)
    return manifest, verified


def run_one_stage(root: Path, run_id: str, stage: str, phase: str, inputs_ref: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one implemented stage after prerequisites; report and stop.

    Unsupported producers stay BLOCKED. No generic import mechanism can label
    externally supplied rows as newly executed production artifacts.
    """
    try:
        manifest, inputs = _stage_inputs(root, run_id, stage, phase, inputs_ref)
        if stage == "4.13":
            from .acceptance_gates import evaluate_quality_artifacts
            result = evaluate_quality_artifacts(root, inputs["quality_inputs"], phase=phase, run_manifest=manifest)
            # A metrics report is useful, but not a completed stage certificate.
            return {"stage": stage, "phase": phase,
                    "status": "FAIL" if result["status"] == "FAIL" else "BLOCKED",
                    "scope": "stage_component_evidence", "component_status": result["status"],
                    "reason": "PILOT_STAGE_CERTIFICATION_INCOMPLETE",
                    "quality": result, "next_stage_executed": False}
        raise RebuildBlocked(f"PRODUCTION_PRODUCER_NOT_ACTIVATED: Stage {stage}")
    except (OSError, ValueError, KeyError) as exc:
        return {"stage": stage, "phase": phase, "status": "BLOCKED", "scope": "stage_preflight",
                "reason": str(exc), "next_stage_executed": False}


def record_stage_report(root: Path, run_id: str, report: dict[str, Any]) -> Path:
    """Record only for an existing verified run; preflight must not invent run state."""
    load_run_manifest(root, run_id)
    payload = {**report, "run_id": run_id, "evaluated_at_real": utc_now_iso(),
               "semantic_sha256": sha256_json({**report, "run_id": run_id})}
    target = get_run_dir(root, run_id) / "reports" / f"acceptance_{uuid4().hex}.json"
    write_json_immutable(target, payload)
    return target
