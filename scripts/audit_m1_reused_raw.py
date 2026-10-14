"""Bounded recovery/hash audit of exactly the raw blobs referenced by v3 memberships."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kg_pipeline.hashing import get_git_info, sha256_file, sha256_json, utc_now_iso  # noqa: E402
from kg_pipeline.rebuild_artifacts import artifact_path  # noqa: E402
from kg_pipeline.storage import write_json_immutable  # noqa: E402

ARCHIVE_SHA256 = "9d72dfce30a63a1048e4e20cc08784a900e3de5d22401f6fe51af96cbedb5184"
RAW_MEMBER = re.compile(r"^data/raw/stage_4_4/blobs/sha256/[0-9a-f]{2}/([0-9a-f]{64})\.bin$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = artifact_path(ROOT, args.output)
    if output.exists():
        parser.error("A fresh output namespace is required")
    archive = ROOT / "outputs/upstream_recovery_release_20261014/kg-data-pre-gate-a-audit-v1.tar.zst"
    if sha256_file(archive) != ARCHIVE_SHA256:
        raise ValueError("Archive hash mismatch")
    memberships = ROOT / "data/KG_lan2/evolving_kg_downstream_v3/tables/document_memberships.parquet"
    input_hash = sha256_file(memberships)
    rows = pq.read_table(memberships).to_pylist()
    required = {r["raw_blob_sha256"] for r in rows}
    if not required or any(not isinstance(d, str) or not re.fullmatch(r"[0-9a-f]{64}", d) for d in required):
        raise ValueError("Every membership must have a valid raw content hash")
    listed = subprocess.run(["tar", "-tf", str(archive)], check=True, capture_output=True, text=True).stdout.splitlines()
    listing_details = subprocess.run(["tar", "-tvf", str(archive)], check=True, capture_output=True, text=True).stdout.splitlines()
    chosen = {}
    for name in listed:
        match = RAW_MEMBER.fullmatch(name)
        if match and match[1] in required:
            if match[1] in chosen:
                raise ValueError("Duplicate selected archive content identity")
            chosen[match[1]] = name
    selected_names = set(chosen.values())
    for line in listing_details:
        # Selected paths contain no spaces and must be regular files, never links.
        if line.split()[-1] in selected_names and not line.startswith("-"):
            raise ValueError("Selected raw member is not a regular file")
    if required - set(chosen):
        raise ValueError(f"Archive missing {len(required - set(chosen))} referenced raw blobs")
    output.mkdir(parents=True)
    selection = output / "selected_members.txt"
    selection.write_text("\n".join(sorted(selected_names)) + "\n", encoding="utf-8")
    recovered = output / "recovered"
    recovered.mkdir()
    subprocess.run(["tar", "-xf", str(archive), "-C", str(recovered), "-T", str(selection)], check=True)
    results = []
    for expected, name in sorted(chosen.items()):
        path = artifact_path(recovered, name)
        actual = sha256_file(path)
        results.append({"member": name, "expected_sha256": expected, "actual_sha256": actual,
                        "bytes": path.stat().st_size, "status": "PASS" if actual == expected else "FAIL"})
    if sha256_file(memberships) != input_hash:
        raise ValueError("v3 input changed during read-only recovery audit")
    commit, dirty = get_git_info(ROOT)
    report = {"scope": "HASH_RECOVERY_AUDIT_ONLY", "scientific_gate_status": "NOT_CERTIFIED",
              "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
              "git_commit": commit, "dirty_state": dirty, "created_at_real": utc_now_iso(),
              "inputs": {"archive_sha256": ARCHIVE_SHA256, "memberships_sha256": input_hash},
              "referenced_raw_count": len(required), "membership_count": len(rows),
              "verified_raw_count": sum(r["status"] == "PASS" for r in results),
              "total_verified_bytes": sum(r["bytes"] for r in results),
              "selection_sha256": sha256_file(selection), "results_semantic_sha256": sha256_json(results),
              "script_sha256": sha256_file(Path(__file__))}
    write_json_immutable(output / "results.json", {"rows": results})
    write_json_immutable(output / "report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
