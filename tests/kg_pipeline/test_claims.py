import pytest
from kg_pipeline.claims import extract_claims
from kg_pipeline.llm_adapter import OfflineMockAdapter

def get_mock_response():
    # Returns a mocked response simulating an LLM extracting facts
    return {
        "claims": [
            {
                "subject_mention": "Company A",
                "relation_name": "CEO",
                "object_mention": "Person B",
                "evidence_span_start": 10,
                "evidence_span_end": 45,
                "is_speculative": False
            },
            {
                "subject_mention": "Empty Span",
                "relation_name": "CEO",
                "object_mention": "Person B",
                "evidence_span_start": 4,
                "evidence_span_end": 5  # whitespace
            },
            {
                "subject_mention": "Hallucinated",
                "relation_name": "IS",
                "object_mention": "Fake",
                # Missing spans!
            },
            {
                "subject_mention": "Out of bounds",
                "relation_name": "IS",
                "object_mention": "Error",
                "evidence_span_start": 0,
                "evidence_span_end": 1000 # Way out of bounds
            }
        ]
    }

def test_extract_claims_offline_cache(tmp_path):
    text = "Here is a text about Company A's CEO Person B."
    cache_dir = tmp_path / "llm_cache"

    # 1. Call with mock to populate cache and test DLQ
    adapter = OfflineMockAdapter(get_mock_response())
    valid_claims, dlq = extract_claims(
        text=text,
        source_id="source_1",
        cache_dir=cache_dir,
        ontology=["CEO", "IS"],
        adapter=adapter
    )

    # Expect 1 valid claim, 2 in dead letter queue (one missing span, one OOB)
    assert len(valid_claims) == 1
    assert valid_claims[0].subject_mention == "Company A"
    assert len(dlq) == 3
    assert "empty or whitespace" in dlq[0]["error"]
    assert "Evidence span offsets are mandatory" in dlq[1]["error"]
    assert "out of bounds" in dlq[2]["error"]

    # 2. Call again with a failing mock callable -> should hit cache and not call it!
    failing_adapter = OfflineMockAdapter({"claims": []})
    def fail(*args): raise RuntimeError("Should not be called")
    failing_adapter.__call__ = fail

    valid_claims2, dlq2 = extract_claims(
        text=text,
        source_id="source_1",
        cache_dir=cache_dir,
        ontology=["CEO", "IS"],
        adapter=failing_adapter
    )

    assert len(valid_claims2) == 1
    assert len(dlq2) == 3

def test_offline_mode_raises_if_not_cached(tmp_path):
    cache_dir = tmp_path / "llm_cache"
    with pytest.raises(RuntimeError, match="Offline mode: No cached response"):
        class FailingAdapter(OfflineMockAdapter):
            def __call__(self, prompt):
                raise RuntimeError(f"Offline mode: No cached response for unseen")

        extract_claims("Unseen text", "s1", cache_dir, ontology=["CEO"], adapter=FailingAdapter({}))
