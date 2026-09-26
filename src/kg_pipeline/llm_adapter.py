import json
import logging
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def generate_extraction_prompt(text: str, ontology: list[str]) -> str:
    """Generate the structured extraction prompt injecting the ontology."""
    ontology_list = ", ".join(f'"{rel}"' for rel in ontology)
    return f"""You are a precise knowledge graph extraction system.
Extract facts from the given text as a list of claims.

RULES:
1. ONLY use the following relations: [{ontology_list}].
2. You must identify the exact character span for your evidence. `evidence_span_start` and `evidence_span_end` are 0-indexed character offsets in the provided text.
3. Determine temporal validity: provide `valid_from_extracted` and `valid_to_extracted` if stated (ISO format).
4. Flag negation (`is_negative`) if the text denies the fact.
5. Flag speculation (`is_speculative`) if the text states a plan, rumor, or future intent.
6. Return valid JSON only.

TEXT:
{text}
"""

class LLMAdapter:
    def __init__(self, model: str, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature

    def __call__(self, prompt: str) -> dict[str, Any]:
        raise NotImplementedError("Subclasses must implement __call__")

class OfflineMockAdapter(LLMAdapter):
    """Used for testing and offline modes. Always returns a preset response or raises."""
    def __init__(self, mock_response: dict[str, Any]):
        super().__init__("offline-mock", 0.0)
        self.mock_response = mock_response

    def __call__(self, prompt: str) -> dict[str, Any]:
        return self.mock_response

class LocalOpenAIAdapter(LLMAdapter):
    """Adapter for vLLM or Ollama running locally using OpenAI-compatible API."""
    def __init__(self, base_url: str, model: str, temperature: float = 0.0):
        super().__init__(model, temperature)
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError(f"LocalOpenAIAdapter only permits localhost endpoints. Got: {base_url}")
        self.base_url = base_url
        try:
            import openai
        except ImportError:
            raise ImportError("The 'openai' package is required for LocalOpenAIAdapter")
        self.client = openai.OpenAI(base_url=self.base_url, api_key="local-placeholder")

    def __call__(self, prompt: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a JSON-only extraction bot."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        return json.loads(content)
