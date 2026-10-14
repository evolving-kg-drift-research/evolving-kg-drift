"""Create a new review package; do not activate schema, edit locks, or invent approvals."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kg_pipeline.acceptance_contract import PublicContract  # noqa: E402
from kg_pipeline.hashing import sha256_file, sha256_json  # noqa: E402
from kg_pipeline.storage import write_json_immutable, write_yaml_immutable  # noqa: E402


def _table(columns: dict[str, tuple[str, bool]], primary: str,
           foreign: dict[str, list[str]] | None = None) -> dict:
    return {"fields": list(columns), "columns": {f: {"arrow_type": t, "nullable": n} for f, (t, n) in columns.items()},
            "primary_key": [primary], "foreign_keys": foreign or {}}


def prepare(root: Path, output: Path) -> dict:
    previous = root / "docs/audit/m1_implementation_20261004/policies"
    matrix_path = previous / "contract_field_matrix.yaml"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    old_manifest = json.loads((previous / "manifest.json").read_text(encoding="utf-8"))
    revision = deepcopy(matrix)
    revision.update({"revision": 2, "status": "REVIEW_REQUIRED", "runtime_apply_allowed": False,
                     "supersedes_physical_sha256": sha256_file(matrix_path)})
    contract = {"schema_version": "1.1.0"}
    for name, table in matrix["tables"].items():
        fields = table["fields"]
        domains = {}
        for f in fields:
            field = f["public_field"]
            if field in {"valid_from", "valid_to", "evidence_observed_at", "accepted_into_kg_at",
                         "retrieved_at_real", "adjudicated_at_real", "mapping_available_at"}:
                domains[field] = "utc_timestamp"
            if field.endswith("confidence"):
                domains[field] = "confidence"
            if field in {"candidate_claim_ids", "supporting_claim_ids"}:
                domains[field] = "sorted_unique_ids"
        contract[name] = {"fields": [f["public_field"] for f in fields],
                          "columns": {f["public_field"]: {"arrow_type": f["proposed_arrow_type"],
                                                         "nullable": f["proposed_nullable"]} for f in fields},
                          "primary_key": table["primary_key"], "foreign_keys": table["foreign_keys"],
                          "domains": domains}
    contract["fact_versions"]["serializer"] = {
        "FactVersionID": "fact_version_id", "LogicalFactID": "logical_fact_id", "url": "source_url"}
    contract["adjudication_decisions"]["serializer"] = {"LogicalFactID": "logical_fact_id"}
    # Auxiliary definitions are proposals requiring exact review, not hidden aliases.
    s, ns, ids = ("string", False), ("string", True), ("list<item: string>", False)
    aux = {
        "canonical_entities": _table({"canonical_entity_id": s, "entity_type": s, "registry_version": s,
            "identity_basis_ref": s, "identity_basis_sha256": s}, "canonical_entity_id"),
        "mention_occurrences": _table({"mention_id": s, "body_variant_id": s, "raw_source_id": s,
            "body_text_sha256": s, "normalization_version": s, "span_start": ("int64", False),
            "span_end": ("int64", False), "raw_form": s, "mention_rule_version": s}, "mention_id",
            {"body_variant_id": ["body_variants", "body_variant_id"],
             "raw_source_id": ["raw_source_versions", "raw_source_id"]}),
        "mapping_decision_provenance": _table({"entity_mapping_id": s, "availability_basis_ref": s,
            "availability_basis_sha256": s, "reviewer_id": s, "reviewed_at_real": s, "policy_sha256": s},
            "entity_mapping_id", {"entity_mapping_id": ["entity_mapping_versions", "entity_mapping_id"]}),
        "claim_evidence": _table({"claim_id": s, "body_variant_id": s, "body_text_sha256": s,
            "evidence_span_start": ("int64", False), "evidence_span_end": ("int64", False),
            "evidence_text_hash": s, "normalization_version": s, "relation_review_ref": ns}, "claim_id",
            {"claim_id": ["claims", "claim_id"], "body_variant_id": ["body_variants", "body_variant_id"]}),
        "evidence_time_provenance": _table({"claim_id": s, "proof_path": s, "proof_sha256": s,
            "observed_at": s, "body_sha256": s, "basis": s, "policy_sha256": s}, "claim_id",
            {"claim_id": ["claims", "claim_id"]}),
        "fact_project_provenance": _table({"FactVersionID": s, "ingested_at_real": s,
            "decision_id": s}, "FactVersionID", {"FactVersionID": ["fact_versions", "FactVersionID"],
            "decision_id": ["adjudication_decisions", "decision_id"]}),
        "source_support_events": _table({"support_event_id": s, "LogicalFactID": s,
            "claim_ids": ids, "independent_origin_ids": ids, "available_at": s, "event_type": s,
            "reviewer_id": s, "basis_ref": s, "basis_sha256": s}, "support_event_id"),
        "extraction_quarantine": _table({"quarantine_id": s, "body_variant_id": s,
            "request_sha256": ns, "reason_code": s, "response_ref": ns, "response_sha256": ns}, "quarantine_id"),
    }
    contract["entity_mapping_versions"]["foreign_keys"]["canonical_entity_id"] = ["canonical_entities", "canonical_entity_id"]
    contract["body_variants"]["fields"].append("normalization_version")
    contract["body_variants"]["columns"]["normalization_version"] = {"arrow_type": "string", "nullable": False}
    contract.update(aux)
    for definition in contract.values():
        if not isinstance(definition, dict):
            continue
        for field in definition["fields"]:
            if field.endswith("_sha256") or field == "evidence_text_hash":
                definition.setdefault("domains", {})[field] = "sha256"
    PublicContract(contract)  # Fail before publishing any incomplete candidate.
    revision["tables"] = {
        name: {"primary_key": definition["primary_key"], "foreign_keys": definition["foreign_keys"],
               "fields": [{"public_field": field,
                           "proposed_arrow_type": definition["columns"][field]["arrow_type"],
                           "proposed_nullable": definition["columns"][field]["nullable"],
                           "runtime_field": definition.get("serializer", {}).get(field, field),
                           "domain": definition.get("domains", {}).get(field, "typed_value"),
                           "migration": "NEW_RUN_ONLY",
                           "source_event": "explicit_producer_or_reviewer_artifact_required"}
                          for field in definition["fields"]]}
        for name, definition in contract.items() if name != "schema_version"
    }
    revision["remaining_review"] = ["source event and eligibility for every new field",
                                    "auxiliary PK/FK and temporal proof contracts",
                                    "exact candidate activation approval"]
    output.mkdir(parents=True, exist_ok=True)
    write_yaml_immutable(output / "contract_field_matrix_v2.yaml", revision)
    write_yaml_immutable(output / "schema_1_1_candidate.yaml", contract)
    for name in ("identity.md", "temporal.md", "support_revision.md", "quality.md", "boundaries.md", "contract.md"):
        target = output / name
        content = (previous / name).read_bytes()
        if target.exists() and target.read_bytes() != content:
            raise ValueError("Refusing to overwrite existing policy revision")
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(content)
    manifest = {"package_version": "m1-acceptance-design-v2", "status": "REVIEW_REQUIRED",
                "runtime_apply_allowed": False, "scope": "typed_contract_and_auxiliary_field_review",
                "previous_matrix_manifest_sha256": old_manifest["files_sha256"]["contract_field_matrix.yaml"],
                "previous_matrix_actual_sha256": sha256_file(matrix_path),
                "previous_matrix_binding_status": "MISMATCH_PRESERVED",
                "files_sha256": {p.name: sha256_file(p) for p in sorted(output.iterdir())
                                 if p.is_file() and p.name != "manifest.json"},
                "candidate_semantic_sha256": sha256_json(contract)}
    write_json_immutable(output / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if ROOT.resolve() not in target.parents:
        parser.error("Review package must be inside the workspace")
    print(json.dumps(prepare(ROOT, target), indent=2))
