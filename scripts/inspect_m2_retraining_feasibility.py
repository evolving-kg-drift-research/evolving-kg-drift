"""Kiểm tra cấu trúc tập xác thực V3.1 trước khi đăng ký huấn luyện lại M2."""
from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, RELEASE_ID, inspect_package, require_current_package  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from kge.splits import coverage_split  # noqa: E402
from kge.validation import fixed_negative_pairs  # noqa: E402

PILOT = "outputs/kge_validation_dev/20261103_t01_three_seed_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục kết quả mới dưới outputs/")
    inputs: dict[str, str] = {}

    def bind(relative: str, digest: str | None = None) -> Path:
        if digest is None:
            digest = sha256_file(ROOT / relative)
        require(inputs.setdefault(relative, digest) == digest, f"Mã băm đầu vào khác nhau: {relative}")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    package = require_current_package(ROOT, ACTIVE_PACKAGE)
    release_file = f"{ACTIVE_PACKAGE.as_posix()}/release_manifest.json"
    candidate = yaml.safe_load(bind("configs/m2_data_3_1_candidate_v2.yaml").read_bytes())
    release = read_json(bind(release_file, candidate["bindings"][release_file]))
    release_hashes = {r["path"]: r["sha256"] for r in release["artifacts"]}
    datasets, preflight = inspect_package(package)
    require(list(datasets) == candidate["snapshots"] and release["release_id"] == RELEASE_ID,
            "Sai danh tính V3.1")
    for path, digest in preflight["input_hashes"].items():
        require(release_hashes.get(path) == digest, f"Sai đầu vào phát hành: {path}")
        bind(f"{ACTIVE_PACKAGE.as_posix()}/{path}", digest)
    pilot_design = yaml.safe_load(bind("configs/m2_pilot.yaml").read_bytes())
    fraction, salt = (pilot_design["validation"][key] for key in ("target_fraction", "salt"))
    pilot_manifest = read_json(bind(f"{PILOT}/experiment_manifest.json"))
    reference = "seed_13/epochs/0050.json"
    checkpoint = bind(f"{PILOT}/{reference}", pilot_manifest["artifacts"]["hashes"][reference])
    reference_vectors = len(datasets["T01"].entities) + len(datasets["T01"].relations)
    epochs = pilot_design["epochs"]
    seeds = pilot_design["seeds"]
    require(seeds == candidate["kge"]["seeds"] == [13, 37, 101], "Sai bộ seed")
    rows = []
    for sid, dataset in datasets.items():
        split = coverage_split(dataset, fraction, salt)
        positives = [t.to_tuple() for t in dataset.triples]
        pairs = fixed_negative_pairs(dataset, split.validation, positives, seed=13)
        rows.append({"snapshot": sid, "bo_ba": len(positives), "huan_luyen": len(split.train),
                     "xac_thuc": len(split.validation), "thuc_the": len(dataset.entities),
                     "quan_he": len(dataset.relations), "cap_am_co_dinh_thu": len(pairs),
                     "ty_le_xac_thuc": len(split.validation) / len(positives)})
    evaluations = len(seeds) * epochs
    result = {
        "trang_thai": "Rà soát khả thi, chưa đăng ký tập xác thực",
        "release_id": RELEASE_ID,
        "kich_ban": {"ty_le_muc_tieu": fraction, "salt_tu_pilot": salt, "epoch_minh_hoa": epochs, "seed": seeds},
        "so_dem_theo_snapshot": rows,
        "so_lan_huan_luyen_moi_luot": len(rows) * len(seeds),
        "so_checkpoint_neu_luu_moi_epoch_xac_thuc": len(rows) * evaluations,
        "uoc_tinh_byte_checkpoint": round(checkpoint.stat().st_size * evaluations
            * sum(row["thuc_the"] + row["quan_he"] for row in rows) / reference_vectors),
        "so_luot_ung_vien_truoc_loc_neu_xep_hang_moi_epoch": evaluations * sum(
            2 * row["xac_thuc"] * row["thuc_the"] for row in rows),
        "so_dong_hang_neu_xep_hang_moi_epoch": evaluations * sum(2 * row["xac_thuc"] for row in rows),
    }
    for path in ("configs/protocol_v1.yaml", "src/kge/splits.py", "src/kge/validation.py",
                 "scripts/inspect_m2_inputs.py", Path(__file__).resolve().relative_to(ROOT).as_posix()):
        bind(path)
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "kha_thi_xac_thuc.json"
    write_json(result_path, result)
    commit, dirty = get_git_info(ROOT)
    manifest = {
        "experiment_id": output.name, "protocol_version": pilot_manifest["protocol_version"], "seed": None,
        "stage": "m2_retraining_feasibility", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**pilot_manifest["inputs"], "data_hash": inputs[release_file], "query_hash": None,
                   "snapshot_hash": content_hash({sid: ds.snapshot_hash for sid, ds in datasets.items()}),
                   "entity_map_hash": content_hash({sid: ds.get_entity_mapping() for sid, ds in datasets.items()}),
                   "relation_map_hash": content_hash({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}),
                   "config_hash": content_hash(result["kich_ban"]), "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {result_path.name: sha256_file(result_path)}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
