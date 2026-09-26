from src.kge.contract import SnapshotDataset
from src.kge.model import TransEConfig
from src.kge.trainer import train_single_seed
from src.drift.pipeline import KGEDriftPipeline


def test_checkpoint_explicit_git_commit_provenance():
    """A28: Checkpoint provenance must record git commit hash and dirty status."""
    ds = SnapshotDataset.create("S1", [("e1", "r1", "e2"), ("e2", "r1", "e3")])
    cfg = TransEConfig(dimension=16, epochs=5, seed=13)

    # 1. Explicit commit passed
    ckpt = train_single_seed(ds, cfg, git_commit="deadbeef1234", git_dirty=True)
    assert ckpt.provenance.git_commit == "deadbeef1234"
    assert ckpt.provenance.git_dirty is True

    # 2. Default resolution
    ckpt_auto = train_single_seed(ds, cfg)
    assert isinstance(ckpt_auto.provenance.git_commit, str)
    assert len(ckpt_auto.provenance.git_commit) > 0
    assert isinstance(ckpt_auto.provenance.git_dirty, bool)


def test_drift_pipeline_records_git_provenance():
    """A28: Drift artifacts must record git commit and dirty status."""
    ds1 = SnapshotDataset.create("S1", [("e1", "r1", "e2"), ("e2", "r1", "e3"), ("e1", "r2", "e3")])
    ds2 = SnapshotDataset.create("S2", [("e1", "r1", "e2"), ("e2", "r1", "e3"), ("e2", "r2", "e3")])

    pipeline = KGEDriftPipeline(
        dimension=16,
        seeds=(13, 37),
        epochs=5,
        git_commit="commit_drift_provenance",
        git_dirty=False,
    )
    results = pipeline.run_on_snapshots({"S1": ds1, "S2": ds2})

    null_art = results["null_artifacts"]["S1"]
    assert null_art.git_commit == "commit_drift_provenance"
    assert null_art.git_dirty is False

    drift_art = results["drift_artifacts"]["S1->S2"]
    assert drift_art.git_commit == "commit_drift_provenance"
    assert drift_art.git_dirty is False
