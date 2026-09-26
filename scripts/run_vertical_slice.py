"""Vertical Slice End-to-End Execution Script.

Connects the full pipeline:
  Articles / Raw Facts -> FactVersions -> Canonical Snapshots (S1, S2, S3)
  -> TransE Multi-Seed Training -> Procrustes Alignment -> Empirical Null -> Longitudinal Drift (SED+)
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is in sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq

from drift.metrics import compute_longitudinal_drift
from drift.null import build_same_snapshot_empirical_null
from drift.procrustes import align_embeddings_procrustes
from drift.anchors import deterministic_hash_split, select_persistent_anchors
from kg_pipeline.contracts import CONTRACT_VERSION
from kg_pipeline.run import init_run, get_run_dir
from kg_pipeline.snapshot_runner import run_snapshots
from kg_pipeline.storage import write_parquet_immutable
from kge.adapter import load_snapshots_from_run
from kge.model import TransEConfig
from kge.trainer import train_multi_seed


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def generate_vertical_slice_facts() -> list[dict]:
    """Generates synthetic facts spanning 2020 to 2023 with verified temporal lineage."""
    facts = []

    # Snapshot 1 (2020): Foundations
    s1_facts = [
        ("GPT_3", "released_by", "OpenAI", dt(2020, 6, 11), "f_01"),
        ("Microsoft", "invested_in", "OpenAI", dt(2019, 7, 22), "f_02"),
        ("BERT", "released_by", "Google", dt(2018, 10, 11), "f_03"),
        ("DeepMind", "acquired_by", "Google", dt(2014, 1, 26), "f_04"),
        ("Sam_Altman", "is_CEO_of", "OpenAI", dt(2019, 3, 1), "f_05"),
        ("Satya_Nadella", "is_CEO_of", "Microsoft", dt(2014, 2, 4), "f_06"),
        ("Sundar_Pichai", "is_CEO_of", "Google", dt(2015, 10, 2), "f_07"),
        ("Mark_Zuckerberg", "is_CEO_of", "Meta", dt(2004, 2, 4), "f_08"),
        ("PyTorch", "released_by", "Meta", dt(2016, 9, 1), "f_09"),
        ("TensorFlow", "released_by", "Google", dt(2015, 11, 9), "f_10"),
    ]

    # Snapshot 2 (2021-2022): Expansions & New Models
    s2_facts = [
        ("DALL_E", "released_by", "OpenAI", dt(2021, 1, 5), "f_11"),
        ("Codex", "released_by", "OpenAI", dt(2021, 8, 10), "f_12"),
        ("GitHub", "acquired_by", "Microsoft", dt(2018, 10, 26), "f_13"),
        ("Codex", "integrated_into", "GitHub", dt(2021, 6, 29), "f_14"),
        ("LaMDA", "released_by", "Google", dt(2021, 5, 18), "f_15"),
        ("AlphaFold_2", "released_by", "DeepMind", dt(2020, 11, 30), "f_16"),
        ("Dario_Amodei", "works_at", "Anthropic", dt(2021, 5, 28), "f_17"),
        ("Claude", "based_on", "Transformer", dt(2021, 6, 1), "f_18"),
    ]

    # Snapshot 3 (2022-2023): ChatGPT, LLaMA, GPT-4
    s3_facts = [
        ("ChatGPT", "released_by", "OpenAI", dt(2022, 11, 30), "f_19"),
        ("GPT_4", "released_by", "OpenAI", dt(2023, 3, 14), "f_20"),
        ("LLaMA", "released_by", "Meta", dt(2023, 2, 24), "f_21"),
        ("PaLM", "released_by", "Google", dt(2022, 4, 4), "f_22"),
        ("ChatGPT", "integrated_into", "Microsoft", dt(2023, 2, 7), "f_23"),
        ("Bard", "released_by", "Google", dt(2023, 3, 21), "f_24"),
    ]

    for subj, rel, obj, obs_at, fid in s1_facts + s2_facts + s3_facts:
        facts.append({
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": f"fv_{fid}",
            "logical_fact_id": f"lf_{subj}_{rel}_{obj}",
            "subject_id": subj,
            "relation_id": rel,
            "object_id": obj,
            "valid_from": obs_at.isoformat(),
            "valid_to": None,
            "evidence_observed_at": obs_at.isoformat(),
            "ingested_at_real": dt(2026, 9, 20).isoformat(),
            "supersedes_version_id": None,
            "revision_type": "creation",
            "source_id": "verified_tech_registry",
            "source_url": f"https://techregistry.org/{fid}",
            "evidence_span_start": 0,
            "evidence_span_end": 20,
            "evidence_text_hash": f"hash_{fid}",
            "extractor_version": "v1_vertical_slice",
            "entity_map_version": "v1",
            "confidence": 0.98,
            "adjudication_status": "AUTO_ACCEPTED",
        })

    return facts


def run_vertical_slice(
    run_id: str = "run_vertical_slice_v02",
    dimension: int = 32,
    epochs: int = 10,
    seeds: tuple[int, ...] = (13, 37, 101),
) -> None:
    print("=" * 70)
    print("STARTING SCIENTIFIC VERTICAL SLICE: EVOLVING KG DRIFT PIPELINE")
    print("=" * 70)

    repo_root = ROOT

    # Step 1: Initialize run & write fact_versions
    print("\n[Step 1] Initializing Run and Persisting Fact Versions...")
    init_run(repo_root, run_id, mode="inventory")
    run_dir = get_run_dir(repo_root, run_id)

    raw_facts = generate_vertical_slice_facts()
    write_parquet_immutable(
        run_dir / "tables" / "fact_versions.parquet",
        "fact_versions",
        raw_facts,
    )
    print(f"  -> Persisted {len(raw_facts)} fact versions to {run_dir / 'tables' / 'fact_versions.parquet'}")

    # Step 2: Build Bitemporal Snapshots (S1, S2, S3)
    print("\n[Step 2] Building Canonical Bitemporal Snapshots (Cutoffs: 2021, 2022, 2023)...")
    snap_summary = run_snapshots(repo_root, run_id)
    for sid, info in snap_summary["snapshots"].items():
        print(f"  -> Snapshot {sid}: {info['num_triples']} triples, {info['num_entities']} entities (Hash: {info['semantic_sha256'][:16]}...)")

    # Step 3: Load into KGE Adapter
    print("\n[Step 3] Loading Snapshots via KGE Input Adapter...")
    datasets = load_snapshots_from_run(repo_root, run_id, snapshot_ids=["S1", "S2", "S3"])
    s1, s2, s3 = datasets["S1"], datasets["S2"], datasets["S3"]
    print(f"  -> S1 Triples: {len(s1.triples)}, Entities: {len(s1.entities)}, Relations: {len(s1.relations)}")
    print(f"  -> S2 Triples: {len(s2.triples)}, Entities: {len(s2.entities)}, Relations: {len(s2.relations)}")
    print(f"  -> S3 Triples: {len(s3.triples)}, Entities: {len(s3.entities)}, Relations: {len(s3.relations)}")

    # Verify deterministic entity mapping identity
    s1_map_hash = s1.compute_mapping_hash()
    print(f"  -> S1 Entity Mapping Hash: {s1_map_hash}")

    # Step 4: Multi-seed TransE Training
    SEEDS = seeds
    DIM = dimension
    EPOCHS = epochs
    print(f"\n[Step 4] Training TransE Multi-Seed Models (Seeds: {SEEDS}, Dim: {DIM}, Epochs: {EPOCHS})...")

    print("  -> Training S1 models...")
    models_s1 = train_multi_seed(s1, seeds=SEEDS, dimension=DIM, epochs=EPOCHS, lr=0.01)
    print("  -> Training S2 models...")
    models_s2 = train_multi_seed(s2, seeds=SEEDS, dimension=DIM, epochs=EPOCHS, lr=0.01)
    print("  -> Training S3 models...")
    models_s3 = train_multi_seed(s3, seeds=SEEDS, dimension=DIM, epochs=EPOCHS, lr=0.01)

    # Invariant: finite embeddings
    for s_name, models in [("S1", models_s1), ("S2", models_s2), ("S3", models_s3)]:
        for seed, ckpt in models.items():
            ckpt.verify_finite()
    print("  -> [Invariant Verified] All checkpoints have 100% finite embeddings (no NaN/Inf).")

    # Step 5: Procrustes Alignment
    print("\n[Step 5] Performing Centered Orthogonal Procrustes Alignment...")
    # Alignment S1 -> S2 (Seed 13)
    common_s1_s2 = select_persistent_anchors(s1.entities, s2.entities)
    split_s1_s2 = deterministic_hash_split(common_s1_s2, fit_ratio=0.6)
    align_s1_s2 = align_embeddings_procrustes(
        models_s1[13].entity_embeddings,
        models_s2[13].entity_embeddings,
        split_s1_s2,
        alignment_type="longitudinal_transition",
    )
    print(f"  -> S1->S2 Orthogonality Error: {align_s1_s2.diagnostics.orthogonality_error:.2e}")
    print(f"  -> S1->S2 Anchor Gap (Holdout - Fit): {align_s1_s2.diagnostics.fit_holdout_gap:.4f}")
    assert align_s1_s2.diagnostics.orthogonality_error < 1e-10, "Orthogonality invariant violated!"

    # Step 6: Empirical Null Modeling
    print("\n[Step 6] Constructing Same-Snapshot Empirical Null Distributions...")
    null_s1 = build_same_snapshot_empirical_null(s1, models_s1)
    null_s2 = build_same_snapshot_empirical_null(s2, models_s2)
    print(f"  -> S1 Null Evaluated Entities: {len(null_s1.entity_displacements)}")
    print(f"  -> S2 Null Evaluated Entities: {len(null_s2.entity_displacements)}")

    # Step 7: Longitudinal Drift (SED+) Measurement
    print("\n[Step 7] Computing Longitudinal Representation Drift (SED+)...")
    drift_s1_s2 = compute_longitudinal_drift(
        checkpoint_prev=models_s1[13],
        checkpoint_next=models_s2[13],
        null_artifact=null_s1,
        transition_id="S1->S2",
    )
    drift_s2_s3 = compute_longitudinal_drift(
        checkpoint_prev=models_s2[13],
        checkpoint_next=models_s3[13],
        null_artifact=null_s2,
        transition_id="S2->S3",
    )

    print("\n" + "=" * 70)
    print("VERTICAL SLICE MEASUREMENT RESULTS (Top Entities S1 -> S2):")
    print(f"{'Entity':<20} | {'Raw Disp':<10} | {'Null Median':<12} | {'SED+':<10}")
    print("-" * 70)
    sorted_meas = sorted(drift_s1_s2.measurements.items(), key=lambda x: x[1].raw_displacement, reverse=True)
    for entity, m in sorted_meas[:8]:
        sed_str = f"{m.sed_plus:.4f}" if m.sed_plus is not None else "N/A"
        null_med_str = f"{m.empirical_null_median:.4f}" if math.isfinite(m.empirical_null_median) else "N/A"
        print(f"{entity:<20} | {m.raw_displacement:<10.4f} | {null_med_str:<12} | {sed_str:<10}")

    # Check invariants
    for e, m in drift_s1_s2.measurements.items():
        assert math.isfinite(m.raw_displacement), f"Non-finite displacement for {e}"
        if m.sed_plus is not None:
            assert m.sed_plus >= 0.0, f"Negative SED+ for {e}"

    print("\n[OK] All hard invariants passed successfully!")
    print("[OK] Complete vertical slice from raw facts to SED+ drift measurement is verified.")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run scientific vertical slice end-to-end")
    parser.add_argument("--run-id", default="run_vertical_slice_v02", help="Run identifier")
    parser.add_argument("--dim", type=int, default=32, help="Embedding dimension")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--seeds", nargs="+", type=int, default=[13, 37, 101], help="Random seeds")
    args = parser.parse_args()

    run_vertical_slice(
        run_id=args.run_id,
        dimension=args.dim,
        epochs=args.epochs,
        seeds=tuple(args.seeds),
    )
