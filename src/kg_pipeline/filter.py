"""Filtering job integrating LLM with Fail-Closed execution."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import uuid

import pyarrow.parquet as pq

from .llm_adapter import LLMAdapter, get_llm_adapter
from .llm_cache import get_cache_key, get_cached_response, set_cached_response
from .run import get_run_dir
from .storage import write_parquet_immutable, read_yaml

logger = logging.getLogger(__name__)


def filter_content(
    text: str,
    source_id: str,
    cache_dir: Path,
    adapter: LLMAdapter,
    policy_guidelines: str
) -> dict[str, str]:
    prompt = f"""Bạn là một trợ lý phân loại nội dung cho dự án Nghiên cứu Temporal Knowledge Graph về AI & Công nghệ số.
Nhiệm vụ của bạn là quyết định xem văn bản sau có thuộc phạm vi của dự án hay không.

Chính sách lọc (Filter Policy):
{policy_guidelines}

Văn bản:
\"\"\"
{text[:4000]}
\"\"\"

Hãy đánh giá và trả về định dạng JSON duy nhất, không giải thích thêm:
{{
    "decision": "include" | "exclude" | "review",
    "reason_code": "Mã lý do ngắn gọn (ví dụ: OUT_OF_DOMAIN, MATCH_AI, TECH_INNOVATION, NOT_RELEVANT)",
    "evidence_snippet": "Đoạn văn bản trích dẫn ngắn chứng minh cho quyết định (nếu có)"
}}
"""
    config = {"temperature": adapter.temperature}
    cache_key = get_cache_key(prompt, adapter.model, config)

    response = get_cached_response(cache_dir, cache_key)
    if response is None:
        # Strict Fail-Closed: API/Quota/Auth errors will raise immediately
        response = adapter(prompt)
        set_cached_response(cache_dir, cache_key, response)

    if not isinstance(response, dict):
        raise ValueError(f"Filter response for {source_id} must be a JSON dict, got: {type(response)}")

    decision = response.get("decision", "review")
    if decision not in ["include", "exclude", "review"]:
        decision = "review"

    return {
        "decision": decision,
        "reason_code": response.get("reason_code", "UNKNOWN"),
        "evidence_snippet": response.get("evidence_snippet", "")
    }


def run_filtering(
    repo_root: Path,
    run_id: str,
    body_variant_ids: list[str],
    body_blobs: list[str],
    adapter: LLMAdapter | None = None,
    llm_mode: str = "hosted",
    model_name: str = "gemini-3.1-flash-lite"
) -> list[dict[str, Any]]:
    run_dir = get_run_dir(repo_root, run_id)

    # Read scope config directly
    scope_path = repo_root / "config" / "corpus_scope.yaml"
    if scope_path.exists():
        scope_config = read_yaml(scope_path)
        policy_guidelines = f"Tập trung vào miền: {scope_config.get('domain', {}).get('name', 'AI & Technology')}.\n"
        policy_guidelines += f"Chủ đề chấp nhận (Included): {', '.join(scope_config.get('included_topics', []))}\n"
        policy_guidelines += f"Chủ đề loại trừ (Excluded): {', '.join(scope_config.get('excluded_topics', []))}\n"
        policy_guidelines += scope_config.get('scope_notes', '')
    else:
        policy_guidelines = "Chỉ giữ các nội dung liên quan tới AI & Technology. Bỏ qua thể thao, giải trí."

    if adapter is None:
        adapter = get_llm_adapter(mode=llm_mode, model=model_name)

    cache_dir = run_dir / "llm_cache"
    cache_dir.mkdir(exist_ok=True, parents=True)

    filter_decisions = []

    for b_id, b_path in zip(body_variant_ids, body_blobs):
        full_path = run_dir / b_path
        if not full_path.is_file():
            continue

        text = full_path.read_text(encoding="utf-8")

        result = filter_content(text, b_id, cache_dir, adapter, policy_guidelines)

        filter_decisions.append({
            "schema_version": "ticket_a_v1",
            "decision_id": f"dec_{uuid.uuid4().hex[:8]}",
            "body_variant_id": b_id,
            "decision": result["decision"],
            "reason_code": result["reason_code"],
            "evidence_snippet": result["evidence_snippet"],
            "filter_version": "v1.0"
        })

    return filter_decisions
