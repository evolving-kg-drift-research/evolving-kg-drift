import json
import hashlib
from pathlib import Path
from typing import Optional, Any

from .storage import write_json_immutable

def get_cache_key(prompt: str, model: str, config: dict[str, Any], system_prompt: Optional[str] = None) -> str:
    """Generate a deterministic cache key for an LLM request."""
    payload = {
        "prompt": prompt,
        "system_prompt": system_prompt or "You are a JSON-only extraction bot.",
        "model": model,
        "config": config
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def get_cached_response(cache_dir: Path, cache_key: str) -> Optional[dict[str, Any]]:
    """Retrieve a cached LLM response if it exists."""
    cache_path = cache_dir / f"{cache_key}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None

def set_cached_response(cache_dir: Path, cache_key: str, response: dict[str, Any]) -> None:
    """Save an LLM response to the cache."""
    cache_path = cache_dir / f"{cache_key}.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_json_immutable(cache_path, response)
