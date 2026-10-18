from kg_pipeline.readiness import raw_input_blockers


def test_mixed_strict_partial_input_blocks():
    assert raw_input_blockers([{"strict_input_eligible": True}, {"strict_input_eligible": False}], [])


def test_empty_input_blocks():
    assert raw_input_blockers([], [])


def test_all_blocking_issue_types_are_honored():
    assert raw_input_blockers(
        [{"strict_input_eligible": True}],
        [{"blocks_strict_input": True, "issue_type": "PARTIAL_ACQUISITION_PROVENANCE"}],
    )


def test_nonblocking_issue_does_not_block_strict_input():
    assert not raw_input_blockers([{"strict_input_eligible": True}], [{"blocks_strict_input": False}])


def test_unknown_eligibility_blocks():
    assert raw_input_blockers([{}], [])
