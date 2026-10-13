"""Internal canonical artifact validation; never certifies a scientific gate.

No KGE imports: Stage 4.18 must create evidence before the public M2 gate opens.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, Sequence

import pyarrow.parquet as pq
import yaml

from temporal.snapshot import (
    SNAPSHOT_BUILDER_VERSION,
    SNAPSHOT_MANIFEST_CONTRACT_VERSION,
    SnapshotEdgeSupport,
    SnapshotExclusion,
    compute_exclusion_semantic_hash,
    compute_entity_mapping_hash,
    compute_support_semantic_hash,
)
from temporal.schema import EntityMappingVersion


class CanonicalTriple(NamedTuple):
    subject_id: str
    relation_id: str
    object_id: str


@dataclass(frozen=True)
class CanonicalSnapshot:
    snapshot_id: str
    triples: tuple[CanonicalTriple, ...]
    snapshot_hash: str

    @classmethod
    def create(cls, snapshot_id: str, triples: Sequence[CanonicalTriple]) -> CanonicalSnapshot:
        if any(not isinstance(value, str) or not value.strip() for row in triples for value in row):
            raise ValueError("Canonical triples require nonempty string identifiers")
        ordered = tuple(sorted(triples))
        if len(ordered) != len(set(ordered)):
            raise ValueError("Canonical graph contains duplicate triples; preserve multiplicity in support")
        digest = hashlib.sha256()
        for subject, relation, obj in ordered:
            digest.update(f"{subject}\t{relation}\t{obj}\n".encode("utf-8"))
        return cls(snapshot_id, ordered, digest.hexdigest())

    @property
    def entities(self) -> list[str]:
        return sorted({entity for row in self.triples for entity in (row.subject_id, row.object_id)})


def _read_snapshot_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest_data = (
            yaml.safe_load(path.read_text(encoding="utf-8"))
            if path.suffix in (".yaml", ".yml")
            else json.loads(path.read_text(encoding="utf-8"))
        )
    except Exception as exc:
        raise ValueError(f"Failed to read snapshot manifest at {path}: {exc}") from exc
    if not isinstance(manifest_data, dict):
        raise ValueError(f"Snapshot manifest must contain a mapping: {path}")
    return manifest_data

logger = logging.getLogger(__name__)


def _load_snapshot_from_parquet(
    parquet_path: Path,
    snapshot_id: str | None = None,
    *,
    verify_manifest: bool = True,
) -> CanonicalSnapshot:
    """Loads a CanonicalSnapshot from a canonical triples.parquet or snapshot_edges.parquet file.

    When verify_manifest is True, verifies physical sidecar hashes and SnapshotManifest integrity.
    """
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Missing triples parquet file: {parquet_path}")

    sid = snapshot_id or parquet_path.parent.name

    # 1. Verify physical sha256 sidecar if present and verification requested
    if verify_manifest:
        sidecar_path = parquet_path.with_name(f"{parquet_path.name}.sha256")
        manifest_sidecar = parquet_path.with_suffix(parquet_path.suffix + ".manifest.json")
        if not sidecar_path.is_file() and not manifest_sidecar.is_file():
            raise ValueError(f"Missing Parquet integrity sidecar: {parquet_path}")
        if sidecar_path.is_file():
            expected_sha = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
            actual_sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Parquet physical SHA-256 sidecar mismatch for {parquet_path.name}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )
        elif manifest_sidecar.is_file():
            try:
                m_info = json.loads(manifest_sidecar.read_text(encoding="utf-8"))
                expected_sha = m_info.get("physical_sha256_computed_at_real")
                actual_sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
                if expected_sha and actual_sha != expected_sha:
                    raise ValueError(
                        f"Parquet physical SHA-256 sidecar mismatch for {parquet_path.name}: "
                        f"expected {expected_sha}, got {actual_sha}"
                    )
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Failed verifying Parquet sidecar {manifest_sidecar}: {e}") from e

    table = pq.read_table(parquet_path)
    triples: list[CanonicalTriple] = []

    sub_col = "subject" if "subject" in table.column_names else "subject_id"
    rel_col = "relation" if "relation" in table.column_names else "relation_id"
    obj_col = "object" if "object" in table.column_names else "object_id"

    for row in table.to_pylist():
        triples.append(
            CanonicalTriple(
                subject_id=row[sub_col],
                relation_id=row[rel_col],
                object_id=row[obj_col],
            )
        )

    dataset = CanonicalSnapshot.create(snapshot_id=sid, triples=triples)

    # 2. Verify snapshot manifest if present and verification requested
    if verify_manifest:
        manifest_path = parquet_path.parent / "snapshot_manifest.yaml"
        if not manifest_path.is_file():
            manifest_path = parquet_path.parent / "snapshot_manifest.json"

        if not manifest_path.is_file():
            raise ValueError(f"Missing snapshot manifest: {parquet_path.parent}")
        if manifest_path.is_file():
            manifest_data = _read_snapshot_manifest(manifest_path)

            if manifest_data.get("manifest_version") != SNAPSHOT_MANIFEST_CONTRACT_VERSION:
                raise ValueError("Snapshot manifest lacks a supported manifest_version")

            # Check graph semantic hash
            exp_graph_hash = manifest_data.get("graph_semantic_hash")
            if not exp_graph_hash:
                raise ValueError("Snapshot manifest lacks graph_semantic_hash")
            if dataset.snapshot_hash != exp_graph_hash:
                raise ValueError(
                    f"Snapshot manifest graph_semantic_hash mismatch: "
                    f"expected {exp_graph_hash}, got {dataset.snapshot_hash}"
                )

            # Dependency fingerprints are mandatory; a historical or provisional
            # manifest cannot silently receive current certification.
            for field in (
                "fact_store_hash",
                "accepted_clock_hash",
                "entity_mapping_hash",
                "resolved_config_hash",
                "boundary_hash",
                "code_fingerprint",
                "support_semantic_hash",
                "exclusion_semantic_hash",
            ):
                if not isinstance(manifest_data.get(field), str) or not re.fullmatch(
                    r"[0-9a-f]{64}", manifest_data[field]
                ):
                    raise ValueError(
                        f"Snapshot manifest lacks a valid dependency SHA-256: {field}"
                    )
            if manifest_data.get("snapshot_builder_version") != SNAPSHOT_BUILDER_VERSION:
                raise ValueError("Snapshot manifest lacks a supported snapshot_builder_version")

            # Check snapshot manifest internal hash
            exp_manifest_hash = manifest_data.get("snapshot_manifest_hash")
            if not exp_manifest_hash:
                raise ValueError("Snapshot manifest lacks snapshot_manifest_hash")
            if exp_manifest_hash:
                semantic = {
                    k: v
                    for k, v in manifest_data.items()
                    if k not in ("created_at_real", "snapshot_manifest_hash")
                }
                computed_manifest_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode("utf-8")).hexdigest()
                if computed_manifest_hash != exp_manifest_hash:
                    raise ValueError(
                        f"Snapshot manifest internal hash mismatch: "
                        f"expected {exp_manifest_hash}, got {computed_manifest_hash}"
                    )
            if manifest_data.get("snapshot_id") != sid:
                raise ValueError(f"Snapshot manifest identity mismatch: {sid}")
            if manifest_data.get("edge_count") != len(dataset.triples):
                raise ValueError(f"Snapshot manifest edge count mismatch: {sid}")

    return dataset


def validate_canonical_snapshots(
    repo_root: Path,
    run_id: str,
    snapshot_ids: Sequence[str] | None = None,
    *,
    verify_manifest: bool = True,
) -> dict[str, CanonicalSnapshot]:
    """Loads all snapshot datasets generated in a pipeline run.

    Returns:
        dict[str, CanonicalSnapshot] ordered by snapshot_id.
    """
    if not verify_manifest:
        raise ValueError("M2 run loading requires verified manifests")
    from kg_pipeline.gates import require_gate_a
    from kg_pipeline.hashing import sha256_json
    from kg_pipeline.run import (
        _producer_ref_for_manifest,
        _producer_ref_for_table,
        get_run_dir,
        load_run_manifest,
        verify_stage_manifest,
    )
    from kg_pipeline.storage import ArtifactConflict, verify_parquet_artifact

    run_manifest = load_run_manifest(repo_root, run_id)
    gate_a_ref = require_gate_a(repo_root, run_id)
    from kg_pipeline.contract_authority import require_schema_compatible
    require_schema_compatible(
        repo_root,
        ["fact_versions", "snapshot_edges", "snapshot_edge_support", "snapshot_exclusions"],
    )
    run_dir = get_run_dir(repo_root, run_id)
    snapshots_dir = run_dir / "snapshots"

    if not snapshots_dir.is_dir():
        raise FileNotFoundError(f"No snapshots directory found in run: {snapshots_dir}")

    results: dict[str, CanonicalSnapshot] = {}

    if snapshot_ids is not None:
        if not snapshot_ids:
            raise ValueError("Explicit snapshot_ids cannot be empty")
        targets = []
        for sid in snapshot_ids:
            if not sid or Path(sid).name != sid or sid in {".", ".."}:
                raise ValueError(f"Invalid snapshot_id: {sid}")
            target = (snapshots_dir / sid).resolve()
            if target.parent != snapshots_dir.resolve():
                raise ValueError(f"Snapshot path escapes run: {sid}")
            targets.append(target)
    else:
        targets = sorted(
            [
                p
                for p in snapshots_dir.iterdir()
                if p.is_dir()
                and ((p / "snapshot_edges.parquet").is_file() or (p / "triples.parquet").is_file())
            ],
            key=lambda p: p.name,
        )

    if not targets:
        raise ValueError(f"No published snapshots in run: {run_id}")
    for target in targets:
        edges_path = target / "snapshot_edges.parquet"
        if not edges_path.is_file() and not (target / "triples.parquet").is_file():
            raise FileNotFoundError(f"Missing requested snapshot edges: {target}")
        if not edges_path.is_file():
            raise ValueError(f"M2 requires canonical snapshot_edges.parquet: {target}")
        if not (target / "snapshot_manifest.yaml").is_file() and not (target / "snapshot_manifest.json").is_file():
            raise ValueError(f"Missing snapshot manifest: {target}")

    for target in targets:
        sid = target.name
        triples_file = target / "snapshot_edges.parquet"
        if not triples_file.is_file():
            triples_file = target / "triples.parquet"

        if not triples_file.is_file():
            raise FileNotFoundError(f"Missing requested snapshot edges: {target}")
        if triples_file.name != "snapshot_edges.parquet":
            raise ValueError(f"M2 requires canonical snapshot_edges.parquet: {target}")
        ref = _producer_ref_for_table(repo_root, triples_file, "snapshot_edges")
        stage = verify_stage_manifest(repo_root, ref["producer_run_id"], ref["producer_stage"])
        if stage.get("gate_a_ref") != gate_a_ref:
            raise ValueError(f"Snapshot stage lacks current Gate A binding: {sid}")
        manifest_path = target / "snapshot_manifest.yaml"
        if not manifest_path.is_file():
            manifest_path = target / "snapshot_manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"Missing snapshot manifest: {target}")
        manifest_ref = _producer_ref_for_manifest(repo_root, manifest_path)
        if (
            manifest_ref.get("producer_run_id") != ref.get("producer_run_id")
            or manifest_ref.get("producer_stage") != ref.get("producer_stage")
            or manifest_ref.get("contract_version") != SNAPSHOT_MANIFEST_CONTRACT_VERSION
        ):
            raise ArtifactConflict(f"Snapshot manifest is not bound by the snapshot producer stage: {sid}")
        manifest_data = _read_snapshot_manifest(manifest_path)
        if manifest_data.get("snapshot_id") != sid:
            raise ArtifactConflict(f"Snapshot manifest identity mismatch: {sid}")
        if manifest_data.get("code_fingerprint") != run_manifest.get("code_fingerprint_sha256"):
            raise ArtifactConflict(f"Snapshot code fingerprint differs from its run: {sid}")
        resolved_config_hash = sha256_json({
            "resolved_config_bundle_semantic_sha256": run_manifest.get("config_bundle_semantic_sha256"),
            "config_candidates": run_manifest.get("config_candidates"),
            "config_approval": run_manifest.get("config_approval"),
            "machine_schema": run_manifest.get("machine_schema"),
        })
        if manifest_data.get("resolved_config_hash") != resolved_config_hash:
            raise ArtifactConflict(f"Snapshot resolved-config hash differs from its run: {sid}")
        bundle_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
        bundle = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        boundary_config = bundle.get("resolved_config", {}).get("snapshot_boundaries")
        if not isinstance(boundary_config, dict) or not boundary_config.get("policy_version"):
            raise ArtifactConflict(f"Snapshot has no versioned frozen boundary policy: {sid}")
        if not any(
            row.get("id") == sid and row.get("cutoff") == manifest_data.get("cutoff")
            for row in boundary_config.get("snapshots", [])
        ):
            raise ArtifactConflict(f"Snapshot cutoff is not one of the configured frozen boundaries: {sid}")
        boundary_hash = sha256_json({
            "snapshot_id": sid,
            "cutoff": manifest_data.get("cutoff"),
            "boundary_policy": boundary_config,
        })
        if manifest_data.get("boundary_hash") != boundary_hash:
            raise ArtifactConflict(f"Snapshot boundary hash differs from its run configuration: {sid}")

        edge_rows = pq.read_table(triples_file).to_pylist()
        edge_ids = {row.get("edge_id") for row in edge_rows}
        if None in edge_ids:
            raise ArtifactConflict(f"Snapshot edges contain a missing edge_id: {sid}")

        companion_rows: dict[str, list[dict[str, Any]]] = {}
        for table_name in ("snapshot_edge_support", "snapshot_exclusions"):
            companion_path = target / f"{table_name}.parquet"
            if not companion_path.is_file():
                raise FileNotFoundError(f"Missing required {table_name} artifact for snapshot {sid}")
            companion_ref = _producer_ref_for_table(repo_root, companion_path, table_name)
            if (
                companion_ref.get("producer_run_id") != ref.get("producer_run_id")
                or companion_ref.get("producer_stage") != ref.get("producer_stage")
            ):
                raise ArtifactConflict(f"Snapshot {table_name} is not bound by the edge producer stage: {sid}")
            verify_parquet_artifact(companion_path, table_name)
            companion_rows[table_name] = pq.read_table(companion_path).to_pylist()

        supports = [
            SnapshotEdgeSupport(**{
                field: row[field]
                for field in (
                    "support_id", "provenance_id", "edge_id", "fact_version_id",
                    "claim_id", "source_version_id", "raw_blob_sha256",
                )
            })
            for row in companion_rows["snapshot_edge_support"]
        ]
        exclusions = [
            SnapshotExclusion(**{
                field: row[field]
                for field in (
                    "exclusion_id", "record_id", "fact_version_id", "reason_code",
                    "severity", "stage", "field", "detail",
                )
            })
            for row in companion_rows["snapshot_exclusions"]
        ]
        if len(supports) != manifest_data.get("support_count"):
            raise ArtifactConflict(f"Snapshot support count mismatch: {sid}")
        if compute_support_semantic_hash(supports) != manifest_data.get("support_semantic_hash"):
            raise ArtifactConflict(f"Snapshot support semantic hash mismatch: {sid}")
        if len(exclusions) != manifest_data.get("exclusion_count"):
            raise ArtifactConflict(f"Snapshot exclusion count mismatch: {sid}")
        if compute_exclusion_semantic_hash(exclusions) != manifest_data.get("exclusion_semantic_hash"):
            raise ArtifactConflict(f"Snapshot exclusion semantic hash mismatch: {sid}")
        for support in supports:
            if support.edge_id not in edge_ids:
                raise ArtifactConflict(f"Snapshot support references an absent edge: {support.edge_id}")
            if not re.fullmatch(r"[0-9a-f]{64}", support.raw_blob_sha256):
                raise ArtifactConflict(f"Snapshot support has an invalid raw evidence hash: {support.support_id}")

        input_refs = stage.get("input_artifacts", [])
        fact_ref = next((item for item in input_refs if item.get("table_name") == "fact_versions"), None)
        provenance_ref = next((item for item in input_refs if item.get("table_name") == "claim_provenance"), None)
        mapping_ref = next((item for item in input_refs if item.get("table_name") == "entity_mapping_versions"), None)
        if fact_ref is None or provenance_ref is None or mapping_ref is None:
            raise ArtifactConflict(f"Snapshot stage omits fact/mapping/provenance input bindings: {sid}")
        fact_path = get_run_dir(repo_root, fact_ref["producer_run_id"]) / fact_ref["path"]
        provenance_path = get_run_dir(repo_root, provenance_ref["producer_run_id"]) / provenance_ref["path"]
        mapping_path = get_run_dir(repo_root, mapping_ref["producer_run_id"]) / mapping_ref["path"]
        fact_rows = pq.read_table(fact_path).to_pylist()
        fact_by_id = {row.get("fact_version_id"): row for row in fact_rows}
        provenance_rows = pq.read_table(provenance_path).to_pylist()
        mapping_rows = pq.read_table(mapping_path).to_pylist()
        mappings: list[EntityMappingVersion] = []
        for row in mapping_rows:
            available_at = row.get("mapping_available_at")
            if not isinstance(available_at, str) or not available_at:
                raise ArtifactConflict(f"Snapshot mapping input has no availability time: {sid}")
            mapping_time = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
            if mapping_time.tzinfo is None or mapping_time.utcoffset() is None:
                raise ArtifactConflict(f"Snapshot mapping input lacks timezone evidence: {sid}")
            mappings.append(EntityMappingVersion(
                entity_mapping_id=row.get("entity_mapping_id") or "",
                mention=row.get("mention") or "",
                canonical_entity_id=row.get("canonical_entity_id") or "",
                mapping_available_at=mapping_time,
                entity_map_version=row.get("entity_map_version") or "",
                supersedes_mapping_id=row.get("supersedes_mapping_id"),
                mapping_basis=row.get("mapping_basis") or "",
                mapping_confidence=float(row.get("mapping_confidence", 1.0)),
            ))
        if compute_entity_mapping_hash(mappings) != manifest_data.get("entity_mapping_hash"):
            raise ArtifactConflict(f"Snapshot mapping hash differs from its bound input: {sid}")
        provenance_keys = {
            (row.get("provenance_id"), row.get("claim_id"), row.get("source_version_id"), row.get("raw_blob_sha256"))
            for row in provenance_rows
        }
        for support in supports:
            fact = fact_by_id.get(support.fact_version_id)
            if fact is None:
                raise ArtifactConflict(f"Snapshot support references an unknown FactVersion: {support.fact_version_id}")
            claim_ids = fact.get("supporting_claim_ids") or []
            if isinstance(claim_ids, str):
                claim_ids = json.loads(claim_ids)
            if support.claim_id not in claim_ids:
                raise ArtifactConflict(f"Snapshot support claim is not attached to its FactVersion: {support.claim_id}")
            provenance_key = (
                support.provenance_id,
                support.claim_id,
                support.source_version_id,
                support.raw_blob_sha256,
            )
            if provenance_key not in provenance_keys:
                raise ArtifactConflict(f"Snapshot support does not resolve to claim provenance: {support.support_id}")
        for exclusion in exclusions:
            if exclusion.fact_version_id not in fact_by_id:
                raise ArtifactConflict(
                    f"Snapshot exclusion references an unknown FactVersion: {exclusion.fact_version_id}"
                )

        dataset = _load_snapshot_from_parquet(
            triples_file, snapshot_id=sid, verify_manifest=True
        )
        results[sid] = dataset
        logger.info(
                "Loaded snapshot %s with %d triples, %d entities",
                sid,
                len(dataset.triples),
                len(dataset.entities),
        )

    if run_manifest.get("scientific_locked") is not True:
        raise PermissionError("Canonical validation requires a run initialized with scientific_locked=true")
    approval = run_manifest.get("config_approval")
    if not isinstance(approval, dict) or approval.get("status") != "FROZEN":
        raise PermissionError("Canonical validation requires a frozen configuration baseline")
    return results
