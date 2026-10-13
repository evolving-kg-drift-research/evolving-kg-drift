"""Bounded read-only recovery inventory. Hash consistency is not certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEARCH_PREFIXES = (
    "sources", "runs", "data/raw", "data/stage_4_3_runs", "data/stage_4_4_runs",
    "data/stage_4_4", "data/event_store", "data/snapshots",
)
REQUIRED = {
    "raw_bytes": ("data/raw/", "data/stage_4_4/"),
    "stage_4_3": ("data/stage_4_3_runs/",),
    "retrievals": ("retrievals.parquet",),
    "source_versions": ("source_versions.parquet", "raw_source_versions.parquet"),
    "memberships": ("document_memberships.parquet",),
    "body_variants": ("body_variants.parquet",),
    "body_text": ("body_blobs/", "body_text/", "bodies/"),
    "claims": ("claims.parquet", "extracted_claims.parquet"),
    "claim_provenance": ("claim_provenance.parquet",),
    "mappings": ("entity_mapping_versions.parquet",),
    "decisions": ("adjudication_decisions.parquet",),
    "extractor_cache": ("extraction_cache/", "extractor_cache/", "llm_cache/"),
    "run_manifests": ("run_manifest.yaml", "run_manifest.json"),
    "stage_manifests": ("stage_manifest.yaml", "stage_manifest.json", "stages/"),
    "gold": ("gold/", "gold.json", "gold.parquet"),
    "gates": ("gates/",),
}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def inventory_root(root: Path) -> list[dict[str, Any]]:
    """Inspect only allowlisted subdirectories; never traverse symlinks/held-out."""
    root = root.resolve()
    if "locked_test" in root.parts:
        raise ValueError("Held-out roots cannot be inventoried")
    items = []
    for prefix in SEARCH_PREFIXES:
        base = root / prefix
        if not base.is_dir() or base.is_symlink() or base.resolve() != base:
            continue
        for directory, dirs, files in os.walk(base, followlinks=False):
            current = Path(directory)
            dirs[:] = sorted(d for d in dirs if d != "locked_test" and not d.startswith(".")
                             and not (current / d).is_symlink()
                             and (current / d).resolve() == current / d)
            for name in sorted(files):
                path = current / name
                if name.startswith(".") or path.is_symlink() or path.resolve() != path:
                    continue
                item: dict[str, Any] = {
                    "root": str(root), "path": path.relative_to(root).as_posix(),
                    "status": "PRESENT_UNVERIFIED", "scope": "current_bytes_only",
                }
                try:
                    payload = path.read_bytes()
                    item.update(bytes=len(payload), sha256=digest(payload))
                    if name.endswith(".parquet"):
                        import pyarrow as pa
                        import pyarrow.parquet as pq
                        table = pq.read_table(pa.BufferReader(payload))
                        item["parquet"] = {"rows": table.num_rows, "fields": table.column_names}
                        sidecar = path.with_suffix(path.suffix + ".manifest.json")
                        if sidecar.is_file() and not sidecar.is_symlink() and sidecar.resolve() == sidecar:
                            declared = json.loads(sidecar.read_text(encoding="utf-8"))
                            expected = declared.get("physical_sha256_computed_at_real")
                            item["sidecar_hash_match"] = expected == item["sha256"] if expected else None
                            if expected and expected != item["sha256"]:
                                item["status"] = "CONFLICTING"
                        else:
                            item["sidecar_hash_match"] = None
                    if name in {"run_manifest.yaml", "gate_A.json"}:
                        # Metadata is evidence, never approval or scientific authority.
                        import yaml
                        document = yaml.safe_load(payload)
                        if isinstance(document, dict):
                            item["declared_metadata"] = {
                                k: document[k] for k in (
                                    "run_id", "mode", "status", "source_lock_status_at_init",
                                    "scientific_locked", "config_approval",
                                ) if k in document
                            }
                except (OSError, ValueError) as exc:
                    item.update(status="CONFLICTING", error=str(exc))
                items.append(item)
    return items


def category_matches(path: str, token: str) -> bool:
    if token.endswith("/"):
        return token in path
    return PurePosixPath(path).name == token


def check_table_links(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check available same-directory tables without inventing missing parents."""
    import pyarrow.parquet as pq
    groups: dict[tuple[str, str], dict[str, Path]] = {}
    for item in items:
        if item["path"].endswith(".parquet") and "parquet" in item:
            path = Path(item["root"]) / item["path"]
            groups.setdefault((item["root"], str(path.parent)), {})[path.stem] = path
    checks = []
    relations = (
        ("source_versions", "retrieval_id", "retrievals", "retrieval_id"),
        ("claim_provenance", "claim_id", "extracted_claims", "claim_id"),
        ("claim_provenance", "membership_id", "document_memberships", "membership_id"),
        ("claim_provenance", "source_version_id", "source_versions", "source_version_id"),
    )
    for (_, directory), tables in sorted(groups.items()):
        for child, child_key, parent, parent_key in relations:
            if child not in tables:
                continue
            result = {"directory": directory, "child": child, "parent": parent,
                      "status": "MISSING", "scope": "reference integrity only"}
            if parent in tables:
                child_table, parent_table = pq.read_table(tables[child]), pq.read_table(tables[parent])
                if child_key in child_table.column_names and parent_key in parent_table.column_names:
                    parent_values = parent_table[parent_key].to_pylist()
                    parent_ids = set(parent_values)
                    values = child_table[child_key].to_pylist()
                    missing = sum(value is None or value not in parent_ids for value in values)
                    duplicates = len(parent_values) - len(parent_ids)
                    status = "CONFLICTING" if missing or duplicates else (
                        "PRESENT_VERIFIED" if values else "PRESENT_UNVERIFIED"
                    )
                    result.update(status=status,
                                  child_rows=len(values), missing_references=missing, duplicate_parent_ids=duplicates)
                    if not values:
                        result["reason"] = "NO_ROWS_TO_VERIFY"
                else:
                    result.update(status="CONFLICTING", reason="REFERENCE_COLUMNS_MISSING")
            checks.append(result)
    return checks


def inventory_zip(path: Path) -> list[dict[str, Any]]:
    """Do not extract. Refuse duplicate/escaping/held-out members before reading."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members")
        if sum(entry.file_size for entry in entries) > 128 * 1024 * 1024:
            raise ValueError("Recovery inventory ZIP exceeds 128 MiB review bound")
        for name in names:
            normalized = PurePosixPath(name.replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts or ":" in name or "locked_test" in normalized.parts:
                raise ValueError("Unsafe or held-out ZIP member; no payload read")
        return [{
            "path": entry.filename, "bytes": entry.file_size,
            "sha256": digest(archive.read(entry)), "status": "PRESENT_UNVERIFIED",
            "scope": "ZIP CRC and current bytes only; no producer/gate certification",
        } for entry in entries if not entry.is_dir()]


def source_candidates(root: Path, ref: str) -> list[dict[str, Any]]:
    lock = json.loads((root / "data/manifests/sources.lock.json").read_text(encoding="utf-8"))
    def blob(path: str) -> bytes:
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=root)
    remote_lock = json.loads(blob("data/manifests/sources.lock.json"))
    results = []
    for role, spec in lock.items():
        payload = blob(spec["path"])
        actual = digest(payload)
        local = root / spec["path"]
        expected = spec["sha256"]
        results.append({
            "role": role, "path": spec["path"], "git_ref": ref,
            "git_blob_sha256": actual, "bytes": len(payload),
            "current_locked_sha256": expected,
            "branch_declared_sha256": remote_lock[role]["sha256"],
            "matches_current_lock": actual == expected,
            "matches_branch_lock": actual == remote_lock[role]["sha256"],
            "local_original_available": local.is_file() and digest(local.read_bytes()) == expected,
            "status": "PRESENT_VERIFIED" if actual == expected else "CONFLICTING",
            "verification_scope": "exact bytes against current source lock only",
            "amendment_approved": False,
        })
    return results


def dependency_inventory(root: Path) -> dict[str, Any]:
    rows = []
    for raw in (root / "requirements.lock.txt").read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, expected = line.split("==", 1)
        try:
            installed = metadata.version(name)
            python_requirement = metadata.metadata(name).get("Requires-Python")
        except metadata.PackageNotFoundError:
            installed, python_requirement = None, None
        rows.append({"package": name, "locked": expected, "installed": installed,
                     "installed_requires_python": python_requirement, "matches_lock": installed == expected})
    return {"python": sys.version, "executable": sys.executable, "packages": rows,
            "locked_environment_verified": all(row["matches_lock"] for row in rows),
            "python_310_runtime_tested": False, "python_311_runtime_tested": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, action="append", default=[])
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Previous reports are immutable; choose a new output")
    roots = list(dict.fromkeys([ROOT, *(p.resolve() for p in args.search_root)]))
    items = [item for root in roots for item in inventory_root(root)]
    archive_items = inventory_zip(args.zip)
    paths = [item["path"] for item in items + archive_items]
    report = {
        "scope": "read_only_recovery_inventory", "production_execution": False,
        "search_roots": [str(root) for root in roots], "allowlisted_prefixes": SEARCH_PREFIXES,
        "excluded": ["locked_test", "symlinks/reparse paths", "hidden entries", "other locations not supplied"],
        "package_sha256": digest(args.zip.read_bytes()), "files": items, "zip_files": archive_items,
        "categories": {category: {
            "status": "PRESENT_UNVERIFIED" if any(any(category_matches(p, token) for token in tokens) for p in paths) else "MISSING",
            "candidates": [p for p in paths if any(category_matches(p, token) for token in tokens)],
        } for category, tokens in REQUIRED.items()},
        "reference_checks": check_table_links(items),
        "source_candidates": source_candidates(ROOT, args.ref),
        "dependencies": dependency_inventory(ROOT),
        "scientific_certification": "BLOCKED",
        "recovery_conclusion": "Presence/hash inspection does not establish provenance or eligibility; no artifact promoted",
    }
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    print(json.dumps({"report": str(args.report), "files": len(items),
                      "categories": dict(Counter(v["status"] for v in report["categories"].values())),
                      "source_candidates": report["source_candidates"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
