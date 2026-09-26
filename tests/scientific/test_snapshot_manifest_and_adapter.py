import hashlib
from datetime import datetime, timezone
from pathlib import Path
import pytest
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from temporal.schema import FactVersion
from temporal.snapshot import (
    SnapshotEdge,
    SnapshotEdgeSupport,
    build_snapshot_edges_and_support,
    compute_graph_semantic_hash,
    compute_support_semantic_hash,
    create_snapshot_manifest,
)
from kge.adapter import load_snapshot_from_parquet


def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_snapshot_hash_semantics_unification(tmp_path: Path):
    """A15: Disambiguate graph_semantic_hash, support_semantic_hash, fact_store_hash, snapshot_manifest_hash."""
    fv1 = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="CompanyX",
        relation_id="is_CEO_of",
        object_id="PersonA",
        valid_from=dt(2022, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2022, 1, 1),
        ingested_at_real=dt(2022, 1, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="trusted_registry_1",
        source_url="http://example.com/1",
        evidence_span_start=10,
        evidence_span_end=20,
        evidence_text_hash="hash1",
        supporting_claim_ids=("claim1",),
    )

    edges, support, exclusions = build_snapshot_edges_and_support(
        [fv1],
        cutoff=dt(2023, 1, 1),
        provenance_map={"fv1": [{
            "provenance_id": "prov1", "claim_id": "claim1",
            "membership_id": "membership1", "source_version_id": "source1",
            "retrieval_id": "retrieval1", "raw_blob_sha256": "d" * 64,
        }]},
    )

    manifest = create_snapshot_manifest(
        snapshot_id="S_2023",
        cutoff=dt(2023, 1, 1),
        edges=edges,
        support_records=support,
        exclusions=exclusions,
        fact_versions=[fv1],
        entity_mapping_hash="ent_map_hash_1",
        resolved_config_hash="cfg_hash_1",
        code_fingerprint="code_fp_1",
    )

    assert manifest.snapshot_id == "S_2023"
    assert manifest.graph_semantic_hash == compute_graph_semantic_hash(edges)
    assert manifest.support_semantic_hash == compute_support_semantic_hash(support)
    assert len(manifest.graph_semantic_hash) == 64
    assert len(manifest.support_semantic_hash) == 64
    assert len(manifest.fact_store_hash) == 64
    assert len(manifest.snapshot_manifest_hash) == 64
    assert manifest.edge_count == 1
    assert manifest.support_count == 1


def test_kge_adapter_verifies_snapshot_manifest_and_detects_tamper(tmp_path: Path):
    """A16: KGE adapter must verify SnapshotManifest integrity, sidecars, and upstream hashes."""
    snapshot_dir = tmp_path / "snapshots" / "S1"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    edge = SnapshotEdge("edge_1", "Alice", "works_at", "Acme", "S1")
    supp = SnapshotEdgeSupport("supp_1", "prov1", "edge_1", "fv1", "c1", "s1", "d" * 64)

    manifest = create_snapshot_manifest(
        snapshot_id="S1",
        cutoff=dt(2023, 1, 1),
        edges=[edge],
        support_records=[supp],
        exclusions=[],
    )

    # Write snapshot_manifest.yaml
    manifest_dict = {
        "snapshot_id": manifest.snapshot_id,
        "cutoff": manifest.cutoff,
        "graph_semantic_hash": manifest.graph_semantic_hash,
        "support_semantic_hash": manifest.support_semantic_hash,
        "fact_store_hash": manifest.fact_store_hash,
        "entity_mapping_hash": manifest.entity_mapping_hash,
        "resolved_config_hash": manifest.resolved_config_hash,
        "code_fingerprint": manifest.code_fingerprint,
        "edge_count": manifest.edge_count,
        "support_count": manifest.support_count,
        "exclusion_count": manifest.exclusion_count,
        "created_at_real": manifest.created_at_real,
        "snapshot_manifest_hash": manifest.snapshot_manifest_hash,
    }
    (snapshot_dir / "snapshot_manifest.yaml").write_text(yaml.safe_dump(manifest_dict), encoding="utf-8")

    # Write snapshot_edges.parquet
    parquet_path = snapshot_dir / "snapshot_edges.parquet"
    table = pa.Table.from_pydict({
        "subject_id": ["Alice"],
        "relation_id": ["works_at"],
        "object_id": ["Acme"],
        "edge_id": ["edge_1"],
        "snapshot_id": ["S1"],
    })
    pq.write_table(table, parquet_path)

    # Write physical sha256 sidecar
    sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    (snapshot_dir / "snapshot_edges.parquet.sha256").write_text(f"{sha}  snapshot_edges.parquet\n", encoding="utf-8")

    # 1. Clean load should succeed
    ds = load_snapshot_from_parquet(parquet_path, verify_manifest=True)
    assert len(ds.triples) == 1
    assert ds.triples[0].subject_id == "Alice"

    # 2. Tampered Parquet content (triples altered) must fail graph_semantic_hash check
    tampered_table = pa.Table.from_pydict({
        "subject_id": ["Alice"],
        "relation_id": ["works_at"],
        "object_id": ["HackedCorp"],
        "edge_id": ["edge_1"],
        "snapshot_id": ["S1"],
    })
    pq.write_table(tampered_table, parquet_path)
    # Even if sidecar updated to match new physical file, semantic hash should fail
    new_sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    (snapshot_dir / "snapshot_edges.parquet.sha256").write_text(f"{new_sha}  snapshot_edges.parquet\n", encoding="utf-8")

    with pytest.raises(ValueError, match="graph_semantic_hash mismatch"):
        load_snapshot_from_parquet(parquet_path, verify_manifest=True)

    # 3. Tampered physical sidecar must fail
    # Restore valid table
    pq.write_table(table, parquet_path)
    (snapshot_dir / "snapshot_edges.parquet.sha256").write_text("bad_hash  snapshot_edges.parquet\n", encoding="utf-8")
    with pytest.raises(ValueError, match="physical SHA-256 sidecar mismatch"):
        load_snapshot_from_parquet(parquet_path, verify_manifest=True)
