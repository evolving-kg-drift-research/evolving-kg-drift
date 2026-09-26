"""Huấn luyện và đánh giá controlled TransE-L2 backbone."""

from .checkpoint import CheckpointProvenance, KGECheckpoint
from .contract import EntityMetadata, SnapshotDataset, Triple
from .fixtures import create_synthetic_snapshots
from .model import TransEConfig, TransEModel
from .trainer import train_multi_seed, train_single_seed

__all__ = [
    "Triple",
    "SnapshotDataset",
    "EntityMetadata",
    "TransEModel",
    "TransEConfig",
    "KGECheckpoint",
    "CheckpointProvenance",
    "train_single_seed",
    "train_multi_seed",
    "create_synthetic_snapshots",
]
