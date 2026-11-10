"""End-to-end execution of Module M4: Recurring QA Panel Evaluation (Stage 8) and Two-Way Fixed Effects Estimation (Stage 9)."""
from __future__ import annotations

from pathlib import Path


def run_m4_pipeline() -> tuple[Path, Path]:
    raise PermissionError(
        "Combined stage execution is disabled. Separate evaluation/statistics stages require "
        "registered inputs and verified empirical pseudo-drift; synthetic replacement is prohibited."
    )


if __name__ == "__main__":
    run_m4_pipeline()
