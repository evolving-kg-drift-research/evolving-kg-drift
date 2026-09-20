import pytest
from kg_pipeline.claims import extract_claims

def mock_llm_callable(prompt, model, config):
    # Returns a mocked response simulating an LLM extracting facts
    return {
        "claims": [
            {
                "subject_mention": "Company A",
                "relation_name": "CEO",
                "object_mention": "Person B",
                "evidence_span_start": 10,
                "evidence_span_end": 19
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
    valid_claims, dlq = extract_claims(
        text=text,
        source_id="source_1",
        cache_dir=cache_dir,
        model="test-model",
        llm_callable=mock_llm_callable
    )
    
    # Expect 1 valid claim, 2 in dead letter queue (one missing span, one OOB)
    assert len(valid_claims) == 1
    assert valid_claims[0].subject_mention == "Company A"
    assert len(dlq) == 2
    assert "Evidence span offsets are mandatory" in dlq[0]["error"]
    assert "Span end is out of bounds" in dlq[1]["error"]
    
    # 2. Call again WITHOUT mock callable -> should hit cache!
    valid_claims2, dlq2 = extract_claims(
        text=text,
        source_id="source_1",
        cache_dir=cache_dir,
        model="test-model",
        llm_callable=None
    )
    
    assert len(valid_claims2) == 1
    assert len(dlq2) == 2
    
def test_offline_mode_raises_if_not_cached(tmp_path):
    cache_dir = tmp_path / "llm_cache"
    with pytest.raises(RuntimeError, match="Offline mode: No cached response"):
        extract_claims("Unseen text", "s1", cache_dir, model="test-model", llm_callable=None)
