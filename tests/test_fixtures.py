"""Tests verifying the properties of the synthetic KGE multi-snapshot fixture."""

from src.kge.fixtures import create_synthetic_snapshots


def test_synthetic_snapshots_properties():
    fixtures = create_synthetic_snapshots()
    assert set(fixtures.keys()) == {"S1", "S2", "S3"}

    s1, s2, s3 = fixtures["S1"], fixtures["S2"], fixtures["S3"]

    # Check triple count constraints (20-100 per snapshot)
    assert 20 <= len(s1.triples) <= 100
    assert 20 <= len(s2.triples) <= 100
    assert 20 <= len(s3.triples) <= 100

    # Check entity count constraints (10-30 entities)
    assert 10 <= len(s1.entities) <= 30
    assert 10 <= len(s2.entities) <= 30
    assert 10 <= len(s3.entities) <= 30

    # Check relation count constraints (3-5 relations)
    assert 3 <= len(s1.relations) <= 5
    assert 3 <= len(s2.relations) <= 5
    assert 3 <= len(s3.relations) <= 5

    # Check persistent entities (E01..E10 present across all 3)
    persistent = {f"E{i:02d}" for i in range(1, 11)}
    assert persistent.issubset(set(s1.entities))
    assert persistent.issubset(set(s2.entities))
    assert persistent.issubset(set(s3.entities))

    # Check removed entities (E11, E12 in S1, not in S2/S3)
    assert "E11" in s1.entities and "E11" not in s2.entities
    assert "E12" in s1.entities and "E12" not in s2.entities

    # Check new entities in S2 (E13, E14)
    assert "E13" not in s1.entities and "E13" in s2.entities and "E13" in s3.entities
    assert "E14" not in s1.entities and "E14" in s2.entities and "E14" in s3.entities

    # Check new entities in S3 (E15, E16)
    assert "E15" not in s1.entities and "E15" not in s2.entities and "E15" in s3.entities
    assert "E16" not in s1.entities and "E16" not in s2.entities and "E16" in s3.entities

    # Check changed edge across snapshots
    s1_e5_rels = [t.relation_id for t in s1.triples if t.subject_id == "E05" and t.object_id == "E06"]
    s2_e5_rels = [t.relation_id for t in s2.triples if t.subject_id == "E05" and t.object_id == "E06"]
    s3_e5_rels = [t.relation_id for t in s3.triples if t.subject_id == "E05" and t.object_id == "E06"]
    assert s1_e5_rels == ["rel_partner_with"]
    assert s2_e5_rels == ["rel_competes_with"]
    assert s3_e5_rels == ["rel_acquired_by"]

    # Verify determinism: calling create_synthetic_snapshots multiple times gives identical hashes
    fixtures_again = create_synthetic_snapshots()
    assert s1.snapshot_hash == fixtures_again["S1"].snapshot_hash
    assert s2.snapshot_hash == fixtures_again["S2"].snapshot_hash
    assert s3.snapshot_hash == fixtures_again["S3"].snapshot_hash
