"""Synthetic multi-snapshot fixtures for KGE training, alignment, and drift testing.

This module provides a controlled, deterministic 3-snapshot sequence (S1, S2, S3)
specifically crafted with:
  - Persistent entities (present across S1, S2, S3)
  - Stable edges (unchanged across snapshots)
  - Changed edges (relations modified or target replaced)
  - Removed edges / retracted facts
  - New entities introduced in later snapshots
  - Entities with diverse degree and frequency profiles for conditional null tests
"""

from __future__ import annotations

from .contract import SnapshotDataset, Triple


def create_synthetic_snapshots() -> dict[str, SnapshotDataset]:
    """Generates deterministic S1, S2, S3 snapshots satisfying the scientific test requirements."""

    # Base persistent triples across all 3 snapshots (stable core)
    stable_triples = [
        Triple("E01", "rel_founder_of", "E02"),
        Triple("E01", "rel_partner_with", "E03"),
        Triple("E02", "rel_competes_with", "E04"),
        Triple("E03", "rel_founder_of", "E04"),
        Triple("E05", "rel_partner_with", "E07"),
        Triple("E06", "rel_founder_of", "E08"),
        Triple("E07", "rel_competes_with", "E08"),
        Triple("E09", "rel_partner_with", "E10"),
        Triple("E01", "rel_partner_with", "E09"),
        Triple("E02", "rel_partner_with", "E10"),
    ]

    # --- SNAPSHOT S1 ---
    # Contains:
    #   - stable_triples
    #   - edges involving E11, E12 (to be removed in S2)
    #   - edge to be modified in S2 (E05 partner_with E06)
    #   - edge to be removed in S2 (E07 partner_with E09)
    s1_triples = list(stable_triples) + [
        Triple("E05", "rel_partner_with", "E06"),      # Will change to competes_with in S2
        Triple("E07", "rel_partner_with", "E09"),      # Will be removed in S2
        Triple("E11", "rel_founder_of", "E12"),        # E11, E12 leave in S2
        Triple("E01", "rel_partner_with", "E11"),      # Leaves in S2
        Triple("E04", "rel_competes_with", "E12"),     # Leaves in S2
        Triple("E08", "rel_partner_with", "E09"),
        Triple("E03", "rel_competes_with", "E05"),
        Triple("E06", "rel_partner_with", "E10"),
        Triple("E02", "rel_founder_of", "E06"),
        Triple("E04", "rel_partner_with", "E08"),
        Triple("E01", "rel_competes_with", "E07"),
        Triple("E02", "rel_partner_with", "E08"),
    ]

    # --- SNAPSHOT S2 ---
    # Transition S1 -> S2:
    #   - E11, E12 removed
    #   - E13, E14 introduced (new entities)
    #   - E05 partner_with E06 -> E05 competes_with E06 (changed edge)
    #   - E07 partner_with E09 removed
    #   - New edges with E13, E14
    s2_triples = list(stable_triples) + [
        Triple("E05", "rel_competes_with", "E06"),     # Changed relation
        Triple("E08", "rel_partner_with", "E09"),      # Preserved
        Triple("E03", "rel_competes_with", "E05"),      # Preserved
        Triple("E06", "rel_partner_with", "E10"),      # Preserved
        Triple("E02", "rel_founder_of", "E06"),        # Preserved
        Triple("E04", "rel_partner_with", "E08"),      # Preserved
        Triple("E01", "rel_competes_with", "E07"),     # Preserved
        Triple("E02", "rel_partner_with", "E08"),      # Preserved
        # New entities and edges in S2:
        Triple("E13", "rel_founder_of", "E14"),
        Triple("E01", "rel_partner_with", "E13"),
        Triple("E04", "rel_competes_with", "E14"),
        Triple("E09", "rel_partner_with", "E13"),
        Triple("E10", "rel_acquired_by", "E14"),
    ]

    # --- SNAPSHOT S3 ---
    # Transition S2 -> S3:
    #   - E15, E16 introduced
    #   - E05 competes_with E06 -> E05 acquired_by E06
    #   - E10 acquired_by E14 preserved
    #   - New edges
    s3_triples = list(stable_triples) + [
        Triple("E05", "rel_acquired_by", "E06"),       # Further changed relation
        Triple("E08", "rel_partner_with", "E09"),
        Triple("E03", "rel_competes_with", "E05"),
        Triple("E06", "rel_partner_with", "E10"),
        Triple("E02", "rel_founder_of", "E06"),
        Triple("E04", "rel_partner_with", "E08"),
        Triple("E01", "rel_competes_with", "E07"),
        Triple("E02", "rel_partner_with", "E08"),
        Triple("E13", "rel_founder_of", "E14"),
        Triple("E01", "rel_partner_with", "E13"),
        Triple("E04", "rel_competes_with", "E14"),
        Triple("E09", "rel_partner_with", "E13"),
        Triple("E10", "rel_acquired_by", "E14"),
        # New entities and edges in S3:
        Triple("E15", "rel_founder_of", "E16"),
        Triple("E02", "rel_partner_with", "E15"),
        Triple("E07", "rel_acquired_by", "E16"),
    ]

    return {
        "S1": SnapshotDataset.create("S1", s1_triples),
        "S2": SnapshotDataset.create("S2", s2_triples),
        "S3": SnapshotDataset.create("S3", s3_triples),
    }
