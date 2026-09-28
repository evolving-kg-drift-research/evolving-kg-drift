import json

import pytest
from kg_pipeline.claims import extract_claims
from kg_pipeline.llm_adapter import OfflineMockAdapter
from kg_pipeline.llm_cache import CacheIntegrityError

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
            },
            {
                "subject_mention": "Invalid Relation",
                "relation_name": "UNKNOWN_REL",
                "object_mention": "Person C",
                "evidence_span_start": 10,
                "evidence_span_end": 45
            },
            {
                "subject_mention": "Unrelated",
                "relation_name": "CEO",
                "object_mention": "Content",
                "evidence_span_start": 0,
                "evidence_span_end": 9 # text[0:9] = "Here is a" (does not contain "Unrelated" or "Content")
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

    # Expect 1 valid claim, 5 in dead letter queue (missing span, OOB, whitespace, invalid relation, unrelated evidence)
    assert len(valid_claims) == 1
    assert valid_claims[0].subject_mention == "Company A"
    assert len(dlq) == 5
    assert "empty or whitespace" in dlq[0]["error"]
    assert "Evidence span offsets are mandatory" in dlq[1]["error"]
    assert "out of bounds" in dlq[2]["error"]
    assert "not in the ontology" in dlq[3]["error"]
    assert "Subject mention is not grounded" in dlq[4]["error"]

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
    assert len(dlq2) == 5


def test_extract_claims_requires_explicit_ontology_cache_and_adapter(tmp_path):
    from temporal.schema import ContractError

    adapter = OfflineMockAdapter({"claims": []})
    with pytest.raises(ContractError, match="explicit versioned ontology"):
        extract_claims(
            "Company A employs Person B.", body_variant_id="body-v1",
            cache_dir=tmp_path / "cache", ontology=None, adapter=adapter,
        )
    with pytest.raises(ContractError, match="run-scoped cache directory"):
        extract_claims(
            "Company A employs Person B.", body_variant_id="body-v1",
            cache_dir=None, ontology=["employs"], adapter=adapter,
        )
    with pytest.raises(ContractError, match="explicitly configured adapter"):
        extract_claims(
            "Company A employs Person B.", body_variant_id="body-v1",
            cache_dir=tmp_path / "cache", ontology=["employs"], adapter=None,
        )

def test_offline_mode_raises_if_not_cached(tmp_path):
    cache_dir = tmp_path / "llm_cache"
    with pytest.raises(RuntimeError, match="Offline mode: No cached response"):
        class FailingAdapter(OfflineMockAdapter):
            def __call__(self, prompt):
                raise RuntimeError("Offline mode: No cached response for unseen")

        extract_claims("Unseen text", "s1", cache_dir, ontology=["CEO"], adapter=FailingAdapter({}))


def test_locked_replay_requires_cached_response_and_never_calls_adapter(tmp_path):
    class NoCallAdapter(OfflineMockAdapter):
        def __call__(self, prompt):
            raise AssertionError("locked replay must not invoke the adapter")

    with pytest.raises(CacheIntegrityError, match="requires an immutable cached response"):
        extract_claims(
            "Company A employs Person B.",
            body_variant_id="body-v1",
            cache_dir=tmp_path / "cache",
            ontology=["employs"],
            adapter=NoCallAdapter({"claims": []}),
            locked_replay=True,
            body_parser_version="body-parser-v1",
            body_parser_fingerprint="b" * 64,
            normalization_version="clean-text-identity-v1",
        )


def test_cache_response_tampering_is_not_treated_as_a_cache_miss(tmp_path):
    text = "Here is a text about Company A's CEO Person B."
    cache_dir = tmp_path / "cache"
    extract_claims(
        text,
        body_variant_id="body-v1",
        cache_dir=cache_dir,
        ontology=["CEO", "IS"],
        adapter=OfflineMockAdapter(get_mock_response()),
        body_parser_version="body-parser-v1",
    )
    cache_path = next(cache_dir.glob("*.json"))
    envelope = json.loads(cache_path.read_text(encoding="utf-8"))
    envelope["response"]["claims"][0]["object_mention"] = "Tampered Entity"
    cache_path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(CacheIntegrityError, match="physical hash mismatch"):
        extract_claims(
            text,
            body_variant_id="body-v1",
            cache_dir=cache_dir,
            ontology=["CEO", "IS"],
            adapter=OfflineMockAdapter({"claims": []}),
            body_parser_version="body-parser-v1",
        )


def test_cache_key_binds_tokenizer_and_input_fingerprints():
    from kg_pipeline.llm_cache import get_cache_key

    common = {"input_sha256": "a" * 64, "tokenizer_revision": "tok-a"}
    changed = {"input_sha256": "a" * 64, "tokenizer_revision": "tok-b"}
    assert get_cache_key("prompt", "model", {}, common) != get_cache_key("prompt", "model", {}, changed)


def test_cache_writer_will_not_repair_a_missing_immutable_manifest(tmp_path):
    from kg_pipeline.llm_cache import get_cache_key, set_cached_response

    fingerprints = {"input_sha256": "a" * 64, "model_revision": "model-r1"}
    response = {"claims": []}
    key = get_cache_key("prompt", "model", {"temperature": 0}, fingerprints)
    cache_dir = tmp_path / "cache"
    set_cached_response(cache_dir, key, response, fingerprints)
    (cache_dir / "manifests" / f"{key}.json").unlink()

    with pytest.raises(CacheIntegrityError, match="incomplete immutable extraction cache pair"):
        set_cached_response(cache_dir, key, response, fingerprints)


def test_locked_replay_requires_normalization_and_parser_fingerprints(tmp_path):
    from temporal.schema import ContractError

    with pytest.raises(ContractError, match="parser/normalization fingerprints"):
        extract_claims(
            "Company A employs Person B.",
            body_variant_id="body-v1",
            cache_dir=tmp_path / "cache",
            ontology=["employs"],
            adapter=OfflineMockAdapter({"claims": []}),
            locked_replay=True,
            body_parser_version="body-parser-v1",
            body_parser_fingerprint="b" * 64,
        )
