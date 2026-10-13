from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit_v3_content_readiness import safe_candidates, select_diagnostic_sample


def test_sample_is_order_independent_and_not_using_outcomes() -> None:
    rows=[{"relation_id":r,"fact_version_id":f"{r}_{i}"} for r in ("r1","r2") for i in range(5)]
    expected=select_diagnostic_sample(rows)
    assert len(expected)==6
    assert expected==select_diagnostic_sample(list(reversed(rows)))
    assert expected==select_diagnostic_sample([{**row,"MRR":99,"drift":-1} for row in rows])


@pytest.mark.parametrize("token", ["../outside","data/locked_test/file","C:/private","/absolute"])
def test_evidence_paths_reject_unsafe_and_heldout(token: str) -> None:
    with pytest.raises(ValueError,match="Unsafe"):
        safe_candidates(token,[Path.cwd()])
