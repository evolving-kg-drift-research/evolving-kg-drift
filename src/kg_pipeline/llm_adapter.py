import os
import sys
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_gemini_api_key() -> str:
    """Resolve Gemini API key from environment or Windows user registry."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg_key:
                val, _ = winreg.QueryValueEx(reg_key, "GEMINI_API_KEY")
                if val:
                    key = val
        except Exception:
            pass
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not configured. Please set the GEMINI_API_KEY environment variable."
        )
    return key


def generate_extraction_prompt(text: str, ontology: list[str]) -> str:
    """Generate the structured extraction prompt injecting the ontology and strict JSON format."""
    ontology_list = ", ".join(f'"{rel}"' for rel in ontology)
    return f"""You are a precise knowledge graph extraction system.
Extract facts from the given text as a list of claims.

RULES:
1. ONLY use the following relation names: [{ontology_list}]. Do NOT invent any other relation name.
2. For each claim, you must identify:
   - "subject_mention": The exact textual mention of the subject entity.
   - "relation_name": One of the allowed relations above.
   - "object_mention": The exact textual mention of the object entity.
   - "evidence_span_start": 0-indexed integer character offset where the supporting evidence starts in the text.
   - "evidence_span_end": 0-indexed integer character offset where the supporting evidence ends in the text.
   - "valid_from_extracted": Temporal start date/time (ISO format or null if not mentioned).
   - "valid_to_extracted": Temporal end date/time (ISO format or null if not mentioned).
   - "is_negative": Boolean (true if the text denies the fact, false otherwise).
   - "is_speculative": Boolean (true if the text states a plan, rumor, or future intent, false otherwise).
3. The extracted evidence span text[evidence_span_start:evidence_span_end] MUST contain either the subject or the object mention verbatim.
4. If no relations from the allowed list are found in the text, return: {{"claims": []}}

JSON Output Schema:
{{
  "claims": [
    {{
      "subject_mention": "...",
      "relation_name": "...",
      "object_mention": "...",
      "evidence_span_start": 0,
      "evidence_span_end": 100,
      "valid_from_extracted": null,
      "valid_to_extracted": null,
      "is_negative": false,
      "is_speculative": false
    }}
  ]
}}

TEXT:
\"\"\"
{text}
\"\"\"
"""


class LLMAdapter:
    def __init__(self, model: str, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature

    def __call__(self, prompt: str) -> dict[str, Any]:
        raise NotImplementedError("Subclasses must implement __call__")


class OfflineMockAdapter(LLMAdapter):
    """Used for offline tests and explicit mock runs. Never touches the network."""
    def __init__(self, mock_response: dict[str, Any]):
        super().__init__("offline-mock", 0.0)
        self.mock_response = mock_response

    def __call__(self, prompt: str) -> dict[str, Any]:
        return self.mock_response


class LocalOpenAIAdapter(LLMAdapter):
    """Adapter for vLLM or Ollama running locally using OpenAI-compatible API."""
    def __init__(self, base_url: str, model: str, temperature: float = 0.0):
        super().__init__(model, temperature)
        self.base_url = base_url
        try:
            import openai
        except ImportError:
            raise ImportError("The 'openai' package is required for LocalOpenAIAdapter")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "local-placeholder"
        self.client = openai.OpenAI(base_url=self.base_url, api_key=api_key)

    def __call__(self, prompt: str) -> dict[str, Any]:
        max_retries = 10
        response = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    timeout=60.0,
                    messages=[
                        {"role": "system", "content": "You are a JSON-only extraction bot."},
                        {"role": "user", "content": prompt}
                    ]
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 3 * (attempt + 1)
                    logger.warning(f"Transient error calling local adapter ({type(e).__name__}: {e}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise

        content = response.choices[0].message.content or ""
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        return json.loads(cleaned)


class GeminiAdapter(LLMAdapter):
    """Adapter for Google Gemini API using google-genai SDK with strict Fail-Closed behavior."""
    def __init__(self, model: str = "gemini-3.1-flash-lite", temperature: float = 0.0):
        super().__init__(model, temperature)
        self.api_key = _resolve_gemini_api_key()
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("The 'google-genai' package is required for GeminiAdapter. Run: pip install google-genai")
        self._genai = genai
        self._types = types
        self.client = genai.Client(api_key=self.api_key)

    def __call__(self, prompt: str) -> dict[str, Any]:
        config = self._types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json",
            system_instruction="You are a precise JSON-only extraction bot. Return ONLY valid JSON matching the requested schema."
        )

        max_retries = 10
        response = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                time.sleep(3.5)  # Pace requests to respect Free Tier 15 RPM limit (~4s per call)
                break
            except Exception as e:
                err_str = f"{type(e).__name__}: {e}"
                is_transient = any(code in err_str.lower() for code in ("503", "429", "unavailable", "resource_exhausted", "deadline", "remoteprotocolerror", "connection", "protocolerror", "http", "socket", "timeout", "readtimeout", "10060", "connecterror"))
                if is_transient and attempt < max_retries - 1:
                    if "429" in err_str or "resource_exhausted" in err_str.lower():
                        wait_time = 30 * (attempt + 1)
                    else:
                        wait_time = 5 * (attempt + 1)
                    logger.warning(f"Transient Gemini API / Network error ({type(e).__name__}). Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                # Fail-Closed: raise real exception when retries fail or non-transient error
                raise

        content_text = response.text
        if not content_text:
            raise ValueError(f"Empty response text received from Gemini API (model={self.model})")

        try:
            return json.loads(content_text)
        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse LLM response as JSON: {content_text}")
            raise ValueError(f"LLM returned invalid JSON payload: {content_text}") from exc


def get_llm_adapter(
    mode: str = "hosted",
    model: str = "ag/gemini-3.7-flash-low",
    temperature: float = 0.0,
    base_url: str | None = None,
    mock_payload: dict[str, Any] | None = None
) -> LLMAdapter:
    """Factory to construct LLM adapters with explicit modes."""
    if mode == "hosted":
        return GeminiAdapter(model=model, temperature=temperature)
    elif mode == "local":
        return LocalOpenAIAdapter(
            base_url=base_url or "http://localhost:20128/v1",
            model=model,
            temperature=temperature
        )
    elif mode == "mock":
        default_mock = mock_payload or {
            "decision": "include",
            "reason_code": "MOCK_EXPLICIT",
            "evidence_snippet": "",
            "claims": []
        }
        return OfflineMockAdapter(default_mock)
    else:
        raise ValueError(f"Unsupported llm_mode: '{mode}'. Allowed: 'hosted', 'local', 'mock'.")
