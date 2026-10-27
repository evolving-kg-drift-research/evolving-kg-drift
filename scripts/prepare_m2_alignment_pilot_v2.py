"""Prepare a hash-bound full pilot inventory; never compute real pilot diagnostics."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.inspect_m2_reuse import source_readiness  # noqa: E402

DEFAULT_CONFIG = Path("configs/m2_alignment_pilot_v2_candidate.yaml")


def source_candidates(git_bytes: bytes, package_bytes: bytes | None) -> dict[str, bytes]:
    """Bounded reversible text encoding/line-ending checks in memory; no restoration."""
    result = {"git_bytes": git_bytes}
    for prefix, payload in (("git", git_bytes), ("package", package_bytes)):
        if payload is None:
            continue
        result[prefix + "_bytes"] = payload
        for decoder in ("utf-8-sig", "utf-16"):
            try:
                text = payload.decode(decoder).replace("\r\n", "\n").replace("\r", "\n")
            except UnicodeError:
                continue
            for ending, value in (("lf", text), ("crlf", text.replace("\n", "\r\n"))):
                for encoder in ("utf-8", "utf-8-sig", "utf-16-le", "utf-16"):
                    result[f"{prefix}_{decoder}_{ending}_{encoder}"] = value.encode(encoder)
    return result


def build_inventory(config: Mapping[str, Any], manifests: Mapping[str, Any], jobs: Sequence[Mapping[str, Any]],
                    plans: Mapping[str, Any]) -> dict[str, Any]:
    snapshots, seeds = config["snapshots"], config["seeds"]
    if (not isinstance(snapshots, list) or len(snapshots) < 2 or len(set(snapshots)) != len(snapshots)
            or any(not isinstance(s, str) or not s.strip() for s in snapshots)
            or seeds != [13, 37, 101] or any(type(s) is not int for s in seeds)):
        raise ValueError("Explicit distinct snapshots and the three registered seeds required")
    expected = {}
    for prev, nxt in zip(snapshots, snapshots[1:]):
        transition = prev + "->" + nxt
        comparisons = [(prev, nxt, s, s, "cross_time") for s in seeds]
        comparisons += [(sid, sid, a, b, "same_snapshot_cross_seed") for sid in (prev, nxt)
                        for a, b in ((13, 37), (13, 101), (37, 101))]
        for src, tgt, a, b, kind in comparisons:
            cid = f"{src}_seed{a}__{tgt}_seed{b}"
            row = {"transition_id": transition, "source_snapshot": src, "target_snapshot": tgt,
                   "source_seed": a, "target_seed": b, "alignment_type": kind, "comparison_id": cid}
            expected[transition, cid] = row
    if len(jobs) != len(expected):
        raise ValueError("Every registered comparison must be included exactly once")
    seen = set()
    for row in jobs:
        key = row.get("transition_id"), row.get("comparison_id")
        if (key not in expected or key in seen or dict(row) != expected[key]
                or type(row["source_seed"]) is not int or type(row["target_seed"]) is not int):
            raise ValueError("Unexpected/duplicate job, altered identity, or outcome input field")
        seen.add(key)
    transitions = [prev + "->" + nxt for prev, nxt in zip(snapshots, snapshots[1:])]
    if set(plans) != set(transitions):
        raise ValueError("Anchor plans must match the full transition inventory")

    def descriptor(run: str, relative: str, manifest: Mapping[str, Any]) -> dict[str, str]:
        digest = manifest["artifacts"]["hashes"].get(relative)
        if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set("0123456789abcdef"):
            raise ValueError("Missing/invalid frozen artifact hash: " + relative)
        return {"path": (Path(run) / relative).as_posix(), "sha256": digest}

    checkpoint_rows = [{"snapshot_id": sid, "seed": seed, **descriptor(config["backbone_run"],
                       f"checkpoints/{sid}/seed_{seed}_repeat_1.json", manifests["backbone"])} for sid in snapshots for seed in seeds]
    inventory, anchor_rows = [], []
    for transition in transitions:
        fit, hold = plans[transition]["split"]["fit_anchors"], plans[transition]["split"]["holdout_anchors"]
        if (not fit or not hold or len(set(fit)) != len(fit) or len(set(hold)) != len(hold) or set(fit) & set(hold)
                or any(not isinstance(e, str) or not e.strip() for e in [*fit, *hold])):
            raise ValueError("Invalid saved disjoint anchor identities")
        anchor_rows.append({"transition_id": transition, "anchor_plan_content_sha256": sha(encode(plans[transition])),
                            "fit_count": len(fit), "holdout_count": len(hold), "selected_ids_changed": False})
        for key in sorted(k for k in expected if k[0] == transition):
            row = expected[key]
            relative = f"alignments/{transition.replace('->', '__')}/{row['comparison_id']}_repeat_1.json"
            inventory.append({**row, **descriptor(config["alignment_run"], relative, manifests["alignment"])})
    return {"version": "m2_alignment_pilot_input_inventory_v2", "status": "PROPOSED_NOT_SCIENTIFICALLY_REGISTERED",
            "scientific_certification": False, "measurement_executed": False,
            "population_selection": "all_registered_adjacent_transition_comparisons", "transitions": transitions,
            "seeds": list(seeds), "checkpoints": checkpoint_rows, "jobs": inventory, "anchors": anchor_rows,
            "downstream_outcomes_used": False, "new_anchor_selection_performed": False}


def prepare(root: Path, config_path: Path) -> Path:
    code = {relative: (ROOT / relative).read_bytes() for relative in
            ("scripts/prepare_m2_alignment_pilot_v2.py", "scripts/inspect_m2_inputs.py", "scripts/inspect_m2_reuse.py",
             "src/drift/measurement_v2.py", "src/kge/contract.py", "src/kge/math_utils.py", "src/kge/checkpoint.py",
             "configs/schemas/m2_alignment_geometry_statistics_v2.schema.yaml")}
    path = safe_file(root, config_path)
    config = yaml.safe_load(path.read_bytes())
    if (set(config) != {"version", "status", "scientific_certification", "parent_config", "backbone_run",
                       "backbone_manifest_sha256", "alignment_run", "alignment_manifest_sha256", "alignment_verification",
                       "snapshots", "seeds", "population_selection", "anchor_plan", "collection", "execution"}
            or config["version"] != "m2_alignment_pilot_plan_v2" or config["status"] != "CANDIDATE_FOR_REGISTRATION"
            or config["scientific_certification"] is not False
            or config["population_selection"] != "all_registered_adjacent_transition_comparisons"
            or config["anchor_plan"] != "reuse_exact_saved_plan_pending_scientific_registration"
            or config["execution"] != {"prepare_only": True, "pilot_execution_allowed": False, "training_allowed": False,
                                      "overwrite_existing_artifacts": False, "auto_execute_next_stage": False, "stop_after_stage_report": True}
            or config["collection"] != {"component_version": "saved_alignment_geometry_statistics_v2", "rank_relative_tolerance": None,
                                        "denominator_handling": "exact_zero_ratio_null_preserve_numerator_and_denominator",
                                        "gap_reporting": "both_signed_and_absolute_descriptive_only", "operating_range_rule": None,
                                        "assign_gate_status": False, "compute_cosine_noise_SED_QA_H1": False}):
        raise ValueError("Preparation-only candidate contract differs; this tool cannot activate a pilot")
    hashes = {path.relative_to(root).as_posix(): sha(path.read_bytes())}

    def bound(relative: str, expected: str) -> Path:
        actual_path = safe_file(root, relative)
        actual = sha(actual_path.read_bytes())
        if actual != expected:
            raise ValueError("Bound pilot input changed: " + relative)
        hashes[relative] = actual
        return actual_path

    parent = yaml.safe_load(bound(config["parent_config"]["path"], config["parent_config"]["sha256"]).read_bytes())
    if (parent["source_baseline"]["policy"] != "preserve_original_hashes"
            or parent["source_baseline"]["replacement_authorized"] is not False
            or config["snapshots"] != parent["snapshots"] or config["seeds"] != parent["kge"]["seeds"]
            or config["backbone_run"] != parent["backbone"]["run"]):
        raise ValueError("Parent baseline/population mismatch")
    for relative, digest in parent["bindings"].items():
        bound(relative, digest)
    sources = source_readiness(root, parent)
    for row in sources["roles"]:
        if row["actual_sha256"] is not None:
            bound(row["path"], row["actual_sha256"])
    manifests = {}
    for name in ("backbone", "alignment"):
        relative = config[name + "_run"] + "/experiment_manifest.json"
        manifest = json.loads(bound(relative, config[name + "_manifest_sha256"]).read_bytes())
        validate_manifest(manifest)
        if manifest["stage"] != ("backbone_training" if name == "backbone" else "alignment") or manifest["scientific_certification"] is not False:
            raise ValueError("Historical artifact scope mismatch")
        manifests[name] = manifest
        for relative, digest in manifest["artifacts"]["hashes"].items():
            bound((Path(config[name + "_run"]) / relative).as_posix(), digest)
    receipt = json.loads(bound(config["alignment_verification"]["path"], config["alignment_verification"]["sha256"]).read_bytes())
    if receipt["status"] != "ALIGNMENT_ARTIFACT_VERIFICATION_PASS" or receipt["manifest_sha256"] != config["alignment_manifest_sha256"]:
        raise ValueError("Historical alignment receipt is not bound")
    alignment = root / config["alignment_run"]
    jobs = json.loads(safe_file(alignment, "registered_jobs.json").read_bytes())
    plans = json.loads(safe_file(alignment, "anchor_plans.json").read_bytes())
    inventory = build_inventory(config, manifests, jobs, plans)
    datasets, package = inspect_package(root / parent["package_root"])
    for relative, digest in package["input_hashes"].items():
        bound((Path(parent["package_root"]) / relative).as_posix(), digest)
    for snapshot in package["snapshots"]:
        old = f"{parent['backbone']['legacy_package_root']}/snapshots/snapshot_{snapshot['snapshot_id']}_canonical.parquet"
        if manifests["backbone"]["inputs"]["hashes"].get(old) != snapshot["physical_sha256"]:
            raise ValueError("Canonical bytes differ from frozen training inputs")
    for transition, plan in plans.items():
        prev, nxt = transition.split("->")
        persistent = set(datasets[prev].entities) & set(datasets[nxt].entities)
        split = plan["split"]
        if (any(e not in persistent for e in [*split["fit_anchors"], *split["holdout_anchors"]])
                or len(split["fit_anchors"]) != parent["alignment"]["fit_count"]
                or len(split["holdout_anchors"]) != parent["alignment"]["holdout_count"]):
            raise ValueError("Saved anchor membership/count mismatch")
    lock = json.loads(safe_file(root, parent["source_baseline"]["lock_path"]).read_bytes())
    targets = {lock[role]["path"]: role for role in ("execution_plan", "patch")}
    listing = subprocess.check_output(["git", "rev-list", "--objects", "--all", "--", *targets], cwd=root, text=True)
    source_search = []
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or parts[1] not in targets:
            continue
        payload = subprocess.check_output(["git", "cat-file", "blob", parts[0]], cwd=root)
        package_relative = (Path(parent["package_root"]) / parts[1]).as_posix()
        try:
            package_path = safe_file(root, package_relative)
        except FileNotFoundError:
            package_path = None
        package_bytes = None if package_path is None else package_path.read_bytes()
        if package_bytes is not None:
            hashes[package_relative] = sha(package_bytes)
        variants = source_candidates(payload, package_bytes)
        expected = lock[targets[parts[1]]]["sha256"]
        source_search.append({"path": parts[1], "git_blob": parts[0], "expected_sha256": expected,
                              "variants": {name: {"bytes": len(data), "sha256": sha(data), "matches_original": sha(data) == expected}
                                           for name, data in variants.items()}, "restoration_performed": False})
    for relative, digest in hashes.items():
        if sha(safe_file(root, relative).read_bytes()) != digest:
            raise ValueError("Input changed during pilot preparation: " + relative)
    for relative, payload in code.items():
        if (ROOT / relative).read_bytes() != payload:
            raise ValueError("Code changed during pilot preparation: " + relative)
    now = datetime.now(timezone.utc)
    out = root / "outputs/m2_alignment_pilot_plan" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "proposed_inventory.json", inventory)
    write_json(out / "resolved_config.json", config)
    write_json(out / "source_search.json", {"source_readiness": sources, "bounded_search": source_search})
    write_json(out / "readiness.json", {"status": "PREPARED_PILOT_NOT_EXECUTED", "scientific_certification": False,
               "G3_evaluated": False, "source_baseline_ready": sources["ready"], "pilot_execution_authorized": False,
               "registration_required": ["exact_original_sources", "scientific_anchor_design_and_frequency",
                                         "pilot_plan_authorization", "rank_tolerance_if_numerical_rank_is_reported",
                                         "operating_range_decision_rule_before_collection"],
               "residual_gap_acceptance_thresholds_required_for_raw_collection": False,
               "measurements_performed": 0, "proposed_comparisons": len(inventory["jobs"])})
    for relative, payload in code.items():
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as f:
            f.write(payload)
        hashes[relative] = sha(payload)
    snapshot_hash = sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()}))
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "git": provenance(), "seed": None,
                "scientific_certification": False, "stage": "alignment_pilot_plan_preparation",
                "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": snapshot_hash, "query_hash": None,
                           "entity_map_hash": sha(encode({sid: ds.get_entity_mapping() for sid, ds in datasets.items()})),
                           "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()})),
                           "config_hash": sha(encode(config)), "hashes": hashes},
                "environment": {"python": platform.python_version(), "os": platform.platform()},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/prepare_m2_alignment_pilot_v2.py"},
                "auto_execute_next_stage": False}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    result = prepare(ROOT, args.config)
    print(json.dumps({"output": result.relative_to(ROOT).as_posix(), "pilot_executed": False, "scientific_certification": False}))
