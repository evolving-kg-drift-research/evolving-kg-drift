"""Shared experiment lineage validation and explicit file bindings."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .hashing import sha256_file

ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"[0-9a-f]{64}")


def bound_file(root: Path, descriptor: dict[str, str]) -> Path:
    relative = Path(descriptor["path"])
    path = (root / relative).resolve()
    if (relative.is_absolute() or not path.is_relative_to(root.resolve())
            or any(p.lower() == "locked_test" for p in path.parts)):
        raise ValueError("Input escapes its allowed root or accesses locked_test")
    if not SHA256.fullmatch(descriptor["sha256"]) or sha256_file(path) != descriptor["sha256"]:
        raise ValueError("Bound artifact hash mismatch")
    return path


def validate_manifest(manifest: dict[str, Any], *, strict: bool = True) -> None:
    schema = yaml.safe_load((ROOT / "configs/schemas/experiment_manifest.schema.yaml").read_bytes())
    if any(k not in manifest for k in schema["required"]):
        raise ValueError("Experiment manifest missing required fields")
    for section, rules in schema["fields"].items():
        required = rules.get("required", [])
        if required and (not isinstance(manifest.get(section), dict)
                         or any(k not in manifest[section] for k in required)):
            raise ValueError(f"Manifest missing nested fields: {section}")
    if manifest["access"]["state"] not in schema["fields"]["access"]["allowed_state"]:
        raise ValueError("Invalid access state")
    if strict:
        if not re.fullmatch(r"[0-9a-f]{40}", manifest["git"]["commit"]):
            raise ValueError("Manifest must bind an actual git commit SHA")
        if type(manifest["git"]["dirty_state"]) is not bool:
            raise ValueError("Manifest dirty_state must be boolean")
        for key in schema["fields"]["inputs"]["required"]:
            value = manifest["inputs"][key]
            if value is None and key in {"query_hash", "snapshot_hash", "entity_map_hash", "relation_map_hash"}:
                continue
            if not isinstance(value, str) or not SHA256.fullmatch(value):
                raise ValueError(f"Invalid input hash: {key}")
        if not manifest["artifacts"]["hashes"]:
            raise ValueError("Manifest must bind output hashes")
        for section in (manifest["inputs"].get("hashes", {}), manifest["artifacts"]["hashes"]):
            for path, digest in section.items():
                if not isinstance(path, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
                    raise ValueError("Invalid artifact hash descriptor")


def verify_artifacts(run: Path) -> dict[str, Any]:
    import json

    manifest = json.loads((run / "experiment_manifest.json").read_bytes())
    validate_manifest(manifest)
    for relative, digest in manifest["artifacts"]["hashes"].items():
        bound_file(run, {"path": relative, "sha256": digest})
    return manifest
