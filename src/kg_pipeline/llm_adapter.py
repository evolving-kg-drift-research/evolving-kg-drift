import json
import logging
from typing import Any

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
        self.model_revision: str | None = None
        self.tokenizer_revision: str | None = None

    def cache_metadata(self) -> dict[str, Any]:
        """Return the frozen request identity used by extraction replay caches."""
        return {
            "adapter_class": f"{type(self).__module__}.{type(self).__qualname__}",
            "model_id": self.model,
            "model_revision": self.model_revision,
            "tokenizer_revision": self.tokenizer_revision,
            "decoding_config": {"temperature": self.temperature},
        }

    def __call__(self, prompt: str) -> dict[str, Any]:
        raise NotImplementedError("Subclasses must implement __call__")

class OfflineMockAdapter(LLMAdapter):
    """Used for testing and offline modes. Always returns a preset response or raises."""
    def __init__(self, mock_response: dict[str, Any]):
        super().__init__("offline-mock", 0.0)
        self.model_revision = "offline-mock-v1"
        self.tokenizer_revision = "not-applicable-v1"
        self.mock_response = mock_response

    def __call__(self, prompt: str) -> dict[str, Any]:
        return self.mock_response

class LocalOpenAIAdapter(LLMAdapter):
    """Adapter for vLLM or Ollama running locally using OpenAI-compatible API."""
    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.0,
        model_revision: str | None = None,
        tokenizer_revision: str | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ):
        super().__init__(model, temperature)
        self.base_url = base_url
        self.model_revision = model_revision
        self.tokenizer_revision = tokenizer_revision
        self.top_p = top_p
        self.max_tokens = max_tokens
        try:
            import openai
        except ImportError:
            raise ImportError("The 'openai' package is required for LocalOpenAIAdapter")
        self.client = openai.OpenAI(base_url=self.base_url, api_key="local-placeholder")

    def cache_metadata(self) -> dict[str, Any]:
        metadata = super().cache_metadata()
        metadata["decoding_config"] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "response_format": "json_object",
        }
        return metadata

    def __call__(self, prompt: str) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a JSON-only extraction bot."},
                {"role": "user", "content": prompt}
            ],
        }
        if self.top_p is not None:
            parameters["top_p"] = self.top_p
        if self.max_tokens is not None:
            parameters["max_tokens"] = self.max_tokens
        response = self.client.chat.completions.create(**parameters)
        content = response.choices[0].message.content
        return json.loads(content)
