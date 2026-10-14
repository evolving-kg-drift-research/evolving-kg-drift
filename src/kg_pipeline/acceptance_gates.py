"""Artifact-backed quality evaluation; no certificate is accepted on status alone."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .acceptance_quality import evaluate_independent_quality
from .acceptance_temporal import observed_at, snapshot_triples
from .hashing import sha256_json
from .rebuild_artifacts import RebuildBlocked, RebuildViolation, read_verified, require_decision, verified_path


def evaluate_quality_artifacts(root: Path, inputs: dict[str, Any], *, phase: str,
                               run_manifest: dict[str, Any]) -> dict[str, Any]:
    refs = inputs.get("references")
    required = {"predictions", "gold", "threshold_annex", "guideline", "sampling_plan"}
    if not isinstance(refs, dict) or set(refs) != required:
        raise RebuildBlocked("Complete independent quality artifact references required")
    documents = {name: read_verified(root, ref) for name, ref in refs.items()}
    gold, sampling, annex = documents["gold"], documents["sampling_plan"], documents["threshold_annex"]
    if (inputs.get("run_manifest_sha256") != run_manifest.get("semantic_sha256")
            or gold.get("guideline_sha256") != refs["guideline"]["sha256"]
            or gold.get("sampling_plan_sha256") != refs["sampling_plan"]["sha256"]
            or sampling.get("selected_article_ids") != gold.get("selected_article_ids")
            or sampling.get("phase") != phase or sampling.get("sampling_locked_before_scoring") is not True):
        raise RebuildBlocked("Quality inputs/sampling/guideline binding differs")
    require_decision(root, inputs.get("procedure_decision_id"), action="approve_quality_procedure", bindings={
        "guideline_sha256": refs["guideline"]["sha256"], "sampling_plan_sha256": refs["sampling_plan"]["sha256"],
        "phase": phase,
    })
    require_decision(root, inputs.get("threshold_decision_id"), action="approve_quality_thresholds", bindings={
        "threshold_annex_sha256": refs["threshold_annex"]["sha256"], "phase": phase,
    })
    approved_sample = set(sampling["selected_article_ids"])
    for article in gold["articles"]:
        if article["article_id"] not in approved_sample or len(article["annotation_refs"]) != 2:
            raise RebuildBlocked("Every gold document requires both original annotations")
        originals = [read_verified(root, ref) for ref in article["annotation_refs"]]
        for index, original in enumerate(originals):
            if (original.get("article_id") != article["article_id"]
                    or original.get("annotator_id") != article["annotator_ids"][index]
                    or original.get("prediction_blind") is not True):
                raise RebuildBlocked("Original annotation identity/independence differs")
        adjudication_ref = article.get("adjudication_ref")
        if not isinstance(adjudication_ref, dict):
            raise RebuildBlocked("Gold requires the disagreement/adjudication record")
        review = read_verified(root, adjudication_ref)
        if (review.get("article_id") != article["article_id"]
                or review.get("adjudicator_id") != article["adjudicator_id"]
                or review.get("annotation_sha256s") != [r["sha256"] for r in article["annotation_refs"]]):
            raise RebuildBlocked("Adjudication does not bind both original annotations")
    # Preserve evaluator code provenance instead of allowing a JSON report to stand in for execution.
    evaluator_ref = inputs.get("evaluator_ref")
    evaluator = verified_path(root, evaluator_ref or {})
    if evaluator.resolve() != (root / "src/kg_pipeline/acceptance_quality.py").resolve():
        raise RebuildBlocked("Quality evaluator code reference differs")
    result = evaluate_independent_quality(documents["predictions"], gold, annex, phase=phase)
    result.update({"input_bindings": {name: ref["sha256"] for name, ref in refs.items()},
                   "evaluator_sha256": evaluator_ref["sha256"],
                   "run_manifest_semantic_sha256": run_manifest["semantic_sha256"]})
    result["quality_report_semantic_sha256"] = sha256_json(result)
    return result


def evaluate_temporal_artifacts(root: Path, run_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Rebuild expected sets and query Neo4j now; never trust an uploaded parity PASS."""
    import os
    from neo4j import GraphDatabase
    from .canonical_validation import validate_canonical_snapshots
    from .neo4j_materializer import _canonical_snapshot_rows, _read_nodes_tx, _read_edges_tx
    from .parity import verify_snapshot_set_parity

    refs = inputs.get("references")
    if not isinstance(refs, dict) or set(refs) != {"facts", "mappings", "boundaries", "temporal_policy", "temporal_proofs"}:
        raise RebuildBlocked("Complete temporal/replay artifact references required")
    values = {name: read_verified(root, ref) for name, ref in refs.items()}
    policy = values["temporal_policy"]
    require_decision(root, inputs.get("policy_decision_id"), action="approve_temporal_replay", bindings={
        "temporal_policy_sha256": refs["temporal_policy"]["sha256"],
        "boundaries_sha256": refs["boundaries"]["sha256"],
    })
    proofs = values["temporal_proofs"]
    indexed_proofs = {}
    for item in proofs:
        if item["FactVersionID"] in indexed_proofs:
            raise RebuildBlocked("Duplicate temporal proof identity")
        proof = read_verified(root, item["proof_ref"])
        result = observed_at(proof, body_sha256=item["body_sha256"], policy=policy)
        indexed_proofs[item["FactVersionID"]] = result
    facts = values["facts"]
    if not facts or set(indexed_proofs) != {f["FactVersionID"] for f in facts}:
        raise RebuildBlocked("Every fact needs independent temporal proof")
    if any(indexed_proofs[f["FactVersionID"]] != f["evidence_observed_at"] for f in facts):
        raise RebuildViolation("Fact observation time differs from its content proof")
    boundaries = values["boundaries"].get("snapshots")
    if not isinstance(boundaries, list) or not boundaries:
        raise RebuildBlocked("Frozen snapshot boundaries missing")
    snapshot_ids = [b["snapshot_id"] for b in boundaries]
    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise RebuildBlocked("Duplicate frozen snapshot identity")
    canonical = validate_canonical_snapshots(root, run_id, snapshot_ids)
    database = inputs.get("database")
    if not isinstance(database, str) or not database.strip() or database.lower() in {"system", "neo4j"}:
        raise RebuildBlocked("Explicit isolated Neo4j database required")
    uri, username, password = (os.environ.get(n) for n in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"))
    if not uri or not username or not password:
        raise RebuildBlocked("Neo4j read-back credentials are unavailable")
    checks = []
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        for boundary in boundaries:
            sid, cutoff = boundary["snapshot_id"], boundary["cutoff"]
            expected, exclusions = snapshot_triples(facts, values["mappings"], cutoff, policy=policy)
            actual = sorted((t.subject_id, t.relation_id, t.object_id) for t in canonical[sid].triples)
            if actual != expected:
                raise RebuildViolation(f"Canonical graph differs from independent as-of reconstruction: {sid}")
            # Permuted inputs must reproduce the exact selected set.
            if snapshot_triples(list(reversed(facts)), list(reversed(values["mappings"])), cutoff,
                                policy=policy) != (expected, exclusions):
                raise RebuildBlocked("Independent replay is nondeterministic")
            nodes, edges, bindings = _canonical_snapshot_rows(root, run_id, sid)
            with driver.session(database=database) as session:
                db_nodes = session.execute_read(_read_nodes_tx, sid)
                db_edges = session.execute_read(_read_edges_tx, sid)
            parity = verify_snapshot_set_parity(nodes, edges, db_nodes, db_edges)
            checks.append({"snapshot_id": sid, "status": parity["status"], "input_bindings": bindings,
                           "graph_replay_sha256": sha256_json(expected), "excluded_count": len(exclusions),
                           "nodes_verified": parity["nodes_verified"], "edges_verified": parity["edges_verified"]})
    return {"status": "PASS", "evaluated_count": len(facts), "snapshots": checks,
            "input_bindings": {name: ref["sha256"] for name, ref in refs.items()},
            "database_read_back_performed": True}
