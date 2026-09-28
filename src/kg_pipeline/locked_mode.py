"""Fail-closed validation for scientific locked replay configurations."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from temporal.schema import ContractError


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_exact_pin(raw: str, *, source: str) -> tuple[str, str]:
    match = re.fullmatch(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)\s*", raw)
    if not match:
        raise ContractError(f"{source} must use exact package==version pins; got {raw!r}.")
    return _normalized_distribution_name(match.group(1)), match.group(2)


def validate_dependency_lock(project_file: Path, lock_file: Path) -> None:
    """Require every direct project dependency to be exactly represented in the lock."""
    try:
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        lock_text = lock_file.read_text(encoding="utf-8")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"Cannot read locked project dependencies: {exc}") from exc
    validate_dependency_lock_content(project, lock_text)


def validate_dependency_lock_content(project: dict[str, Any], lock_text: str) -> None:
    """Validate parsed project metadata and its lock text without filesystem access."""
    dependencies = project.get("project", {}).get("dependencies")
    if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
        raise ContractError("pyproject.toml must declare project.dependencies as a list of requirements.")
    locked: dict[str, str] = {}
    for line_number, raw_line in enumerate(lock_text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        name, version = _parse_exact_pin(line, source=f"requirements.lock.txt:{line_number}")
        if name in locked and locked[name] != version:
            raise ContractError(f"requirements.lock.txt has conflicting pins for {name}.")
        locked[name] = version

    for raw_requirement in dependencies:
        name, version = _parse_exact_pin(raw_requirement, source="pyproject.toml dependency")
        if locked.get(name) != version:
            raise ContractError(
                f"Direct dependency {name}=={version} is not exactly pinned in requirements.lock.txt."
            )


def scientific_locked_flag(config: dict[str, Any]) -> bool:
    value = config.get("scientific_locked", False)
    if type(value) is not bool:
        raise ContractError("scientific_locked must be a YAML boolean, not a truthy string or number.")
    return value


def validate_scientific_locked_run(
    config: dict[str, Any],
    run_manifest: dict[str, Any],
    *,
    adapter_metadata: dict[str, Any] | None = None,
) -> None:
    """Require frozen dependencies and a fully pinned local extraction request."""
    if not scientific_locked_flag(config):
        raise ContractError("Scientific locked mode is not enabled for this run.")
    if run_manifest.get("scientific_locked") is not True:
        raise ContractError("Run manifest does not bind scientific_locked=true.")
    validate_locked_baseline(config, run_manifest)

    resolved = config.get("resolved_config", {})
    adapter = resolved.get("llm_adapter") or config.get("llm_adapter")
    validate_local_adapter_declaration(adapter)
    metadata = adapter_metadata or {}
    for name in ("model_revision", "tokenizer_revision"):
        if metadata.get(name) != adapter[name]:
            raise ContractError(f"Scientific locked adapter fingerprint does not match llm_adapter.{name}.")


def validate_local_adapter_declaration(adapter: Any, *, require_pins: bool = True) -> None:
    """Validate that extraction uses an explicit local adapter declaration."""
    if not isinstance(adapter, dict) or adapter.get("type") != "local":
        raise ContractError("Scientific extraction requires an explicitly declared local inference adapter.")
    required = ("model", "model_revision", "tokenizer_revision") if require_pins else ("model",)
    for name in required:
        if not isinstance(adapter.get(name), str) or not adapter[name].strip():
            qualifier = "pinned " if require_pins else "explicit "
            raise ContractError(f"Scientific extraction requires {qualifier}llm_adapter.{name}.")
    if require_pins:
        for name in ("temperature", "top_p", "max_tokens"):
            if name not in adapter:
                raise ContractError(f"Scientific locked extraction requires explicit llm_adapter.{name}.")
        if isinstance(adapter["temperature"], bool) or not isinstance(adapter["temperature"], (int, float)):
            raise ContractError("Scientific locked extraction requires numeric llm_adapter.temperature.")
        if adapter["top_p"] is not None and (
            isinstance(adapter["top_p"], bool) or not isinstance(adapter["top_p"], (int, float))
        ):
            raise ContractError("Scientific locked extraction requires numeric or null llm_adapter.top_p.")
        if adapter["max_tokens"] is not None and (
            isinstance(adapter["max_tokens"], bool)
            or not isinstance(adapter["max_tokens"], int)
        ):
            raise ContractError("Scientific locked extraction requires integer or null llm_adapter.max_tokens.")
    base_url = adapter.get("base_url")
    parsed = urlparse(base_url) if isinstance(base_url, str) else None
    if parsed is None or parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost", "127.0.0.1", "::1",
    }:
        raise ContractError("Scientific extraction permits only an explicitly local inference endpoint.")


def validate_locked_baseline(config: dict[str, Any], run_manifest: dict[str, Any]) -> None:
    """Validate the approved dependency set independently of a specific stage."""
    if not scientific_locked_flag(config):
        raise ContractError("Scientific locked mode is not enabled for this run.")
    if run_manifest.get("scientific_locked") is not True:
        raise ContractError("Run manifest does not bind scientific_locked=true.")
    approval = run_manifest.get("config_approval")
    if not isinstance(approval, dict) or approval.get("status") != "FROZEN":
        raise ContractError("Scientific locked mode requires an approved, frozen configuration baseline.")
    candidates = run_manifest.get("config_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("Scientific locked mode requires the initialized dependency fingerprint set.")
    for relative in ("pyproject.toml", "requirements.lock.txt"):
        dependency = next((item for item in candidates if item.get("path") == relative), None)
        if not isinstance(dependency, dict) or not dependency.get("exists") or not dependency.get("sha256"):
            raise ContractError(f"Scientific locked mode requires {relative} bound to the run.")
