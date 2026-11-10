"""Retired hard-coded drift runner. Use the registered single-stage runner."""
from __future__ import annotations

from pathlib import Path


def run_drift_stage_all() -> Path:
    raise PermissionError(
        "Legacy drift execution is disabled; use run_m2_measurement_v2.py with a registered "
        "explicit config/input plan. Historical run paths must not be reused implicitly."
    )


if __name__ == "__main__":
    run_drift_stage_all()
