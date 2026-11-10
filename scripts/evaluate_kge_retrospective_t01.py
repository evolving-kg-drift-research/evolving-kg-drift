"""Chấm đối chứng hồi cứu T01 theo đúng gói thiết kế đã đối chiếu."""
from __future__ import annotations

import argparse
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib
import numpy as np
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, SEEDS, Triple, bound_file, content_hash, get_git_info, json_bytes,
    prepare, read_json, require, sha256_file, validate_manifest, verify_artifacts, write_json,
)
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.math_utils import l2_norm  # noqa: E402
from scripts.evaluate_legacy_t01 import metrics, rank_query  # noqa: E402

CANDIDATE = ROOT / "outputs/kge_retrospective_t01_candidate/20261104_t01_v2"
INDICATORS = ("MRR", "Hits@1", "Hits@10")
BASELINE = "tan_suat"


def calculate(
    design: dict[str, Any], queries: list[dict[str, Any]], train: list[list[str]],
    checkpoints: dict[str, KGECheckpoint],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    candidates = design["candidates"]
    frequency = Counter(entity for h, _, t in train for entity in (h, t))
    ranks: dict[str, list[dict[str, Any]]] = {method: [] for method in (BASELINE, *checkpoints)}
    for query in queries:
        triple = tuple(query["triple"])
        h, r, t = triple
        side = query["side"]
        index = 0 if side == "head" else 2
        positives = {(entity, r, t) if side == "head" else (h, r, entity)
                     for entity in query["filtered_entities"]}
        baseline = rank_query(triple, side, candidates, positives, lambda alt: float(frequency[alt[index]]))
        ranks[BASELINE].append({"query_id": query["query_id"], **baseline})
        for method, checkpoint in checkpoints.items():
            def score(alt: Triple) -> float:
                head, relation, tail = alt
                return -l2_norm([a + b - c for a, b, c in zip(
                    checkpoint.entity_embeddings[head], checkpoint.relation_embeddings[relation],
                    checkpoint.entity_embeddings[tail], strict=True)])

            row = rank_query(triple, side, candidates, positives, score)
            ranks[method].append({"query_id": query["query_id"], **row})
    values = {method: {k: value for k, value in metrics(rows).items() if k in INDICATORS}
              for method, rows in ranks.items()}
    average = {k: mean(values[str(seed)][k] for seed in SEEDS) for k in INDICATORS}
    deltas = {str(seed): {k: values[str(seed)][k] - values[BASELINE][k] for k in INDICATORS} for seed in SEEDS}
    summary = {"so_truy_van": len(queries), "chi_so": values, "trung_binh_ba_seed": average,
               "chenh_lech_so_voi_tan_suat": deltas,
               "chenh_lech_trung_binh": {k: mean(deltas[str(seed)][k] for seed in SEEDS) for k in INDICATORS}}
    return ranks, summary


def verify_scores(
    candidates: list[str], queries: list[dict[str, Any]], train: list[list[str]],
    checkpoints: dict[str, KGECheckpoint], ranks: dict[str, Any], summary: dict[str, Any],
) -> dict[str, Any]:
    index = {e: i for i, e in enumerate(candidates)}
    frequencies = np.bincount([index[entity] for h, _, t in train for entity in (h, t)], minlength=len(candidates))
    matrices = {method: np.array([model.entity_embeddings[e] for e in candidates])
                for method, model in checkpoints.items()}
    checked_scores = 0
    for method, rows in ranks.items():
        checked_ranks = []
        for query, row in zip(queries, rows, strict=True):
            h, r, t = query["triple"]
            if method == BASELINE:
                scores = frequencies
            else:
                matrix = matrices[method]
                relation = np.array(checkpoints[method].relation_embeddings[r])
                offsets = matrix + relation - matrix[index[t]] if query["side"] == "head" else (
                    matrix[index[h]] + relation - matrix)
                scores = -np.linalg.norm(offsets, axis=1)
            filtered = set(query["filtered_entities"])
            surviving = [e for e in candidates if e not in filtered]
            expected = scores[[index[e] for e in surviving]]
            saved_ids, saved_scores = zip(*row["candidate_scores"], strict=True)
            target = scores[index[query["target"]]]
            better, tied = int(np.count_nonzero(expected > target)), int(np.count_nonzero(expected == target))
            rank = better + (tied + 1) / 2
            require(row["query_id"] == query["query_id"] and row["triple"] == query["triple"]
                    and row["side"] == query["side"] and list(saved_ids) == surviving
                    and row["candidate_count"] == len(surviving) == query["candidate_count_after_filter"]
                    and row["filtered_count"] == len(filtered)
                    and row["better"] == better and row["tied_including_target"] == tied
                    and row["rank"] == rank and row["reciprocal_rank"] == 1 / rank
                    and np.isclose(row["target_score"], target, rtol=1e-13, atol=1e-13)
                    and np.allclose(saved_scores, expected, rtol=1e-13, atol=1e-13),
                    f"Đối chiếu thứ hạng thất bại ở {method}/{query['query_id']}")
            checked_scores += len(surviving)
            checked_ranks.append(rank)
        array = np.array(checked_ranks)
        np.testing.assert_allclose([summary["chi_so"][method][key] for key in INDICATORS],
                                   [np.mean(1 / array), np.mean(array <= 1), np.mean(array <= 10)],
                                   rtol=0, atol=1e-14)
    for key in INDICATORS:
        vals = np.array([summary["chi_so"][str(seed)][key] for seed in SEEDS])
        deltas = vals - summary["chi_so"][BASELINE][key]
        np.testing.assert_allclose([summary["chenh_lech_so_voi_tan_suat"][str(seed)][key] for seed in SEEDS],
                                   deltas, rtol=0, atol=1e-14)
        np.testing.assert_allclose([summary["trung_binh_ba_seed"][key], summary["chenh_lech_trung_binh"][key]],
                                   [vals.mean(), deltas.mean()], rtol=0, atol=1e-14)
    return {"trang_thai": "Đã đối chiếu", "so_dong_thu_hang": len(queries) * len(ranks),
            "so_diem_ung_vien": checked_scores, "cach_doi_chieu": "Tính lại điểm bằng mảng NumPy"}


def plot(path: Path, summary: dict[str, Any]) -> None:
    fig = Figure(figsize=(11.3, 4.9), facecolor="#ffffff", layout="none")
    axes = fig.subplots(1, 3, sharey=True)
    fig.subplots_adjust(left=.083, right=.979, bottom=.23, top=.75, wspace=.20)
    fig.text(.083, .94, "Dự đoán liên kết trên 26 bộ ba xuất hiện sau T01",
             fontsize=19, weight="bold", color="#182839")
    fig.text(.083, .86, "52 truy vấn · TransE-L2 tại vòng 50 so với đối chứng tần suất",
             fontsize=11.5, color="#44566a")
    labels = ("Tần suất", "Khởi tạo\n13", "Khởi tạo\n37", "Khởi tạo\n101")
    colors = ("#738398", "#126768", "#157e7c", "#23928e")
    values = summary["chi_so"]
    upper = max(.10, max(values[method][k] for method in values for k in INDICATORS) * 1.27)
    for ax, key in zip(axes, INDICATORS, strict=True):
        heights = [values[method][key] for method in (BASELINE, *map(str, SEEDS))]
        bars = ax.bar(labels, heights, color=colors, width=.65, zorder=3)
        for bar, value in zip(bars, heights, strict=True):
            label = (f"{value:.3f}" if key == "MRR" else f"{value:.1%}").replace(".", ",")
            ax.annotate(label, (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=9, color="#182839")
        ax.set_title(key, loc="left", weight="bold", pad=10, color="#182839")
        ax.set_ylim(0, upper)
        ax.yaxis.set_major_formatter(lambda value, _: f"{value:.2f}".replace(".", ","))
        ax.tick_params(axis="x", length=0, pad=7, labelsize=9)
        ax.tick_params(axis="y", length=0, labelsize=9)
        ax.grid(axis="y", color="#e5ecf0", zorder=0)
        for name in ("top", "right", "left"):
            ax.spines[name].set_visible(False)
        ax.spines["bottom"].set_color("#c0cbd5")
    axes[0].set_ylabel("Giá trị chỉ số (thang 0–1)")
    fig.text(.083, .075, "Đánh giá hồi cứu · 26/1.084 bộ ba sau T01 có đủ định danh đã thấy khi huấn luyện",
             fontsize=10, color="#44566a")
    with path.open("xb") as stream:
        fig.savefig(stream, format="png", dpi=180)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--design-hash", required=True, help="SHA-256 của thiết kế đã duyệt để chấm hồi cứu")
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and all(p.lower() != "locked_test" for p in output.parts)
            and not output.exists(), "Cần thư mục kết quả mới dưới outputs/")
    parent = verify_artifacts(CANDIDATE)
    design, artifacts, inputs = prepare()
    require(parent["inputs"]["config_hash"] == content_hash(design) == args.design_hash
            and parent["inputs"]["query_hash"] == content_hash(artifacts["queries.json"])
            and parent["inputs"]["hashes"] == inputs
            and set(parent["artifacts"]["hashes"]) == set(artifacts), "Gói thiết kế không khớp")
    for name, data in artifacts.items():
        require((CANDIDATE / name).read_bytes() == json_bytes(data), f"Thiết kế lưu không khớp: {name}")
    for path in (*(CANDIDATE / name for name in (*artifacts, "experiment_manifest.json")), Path(__file__)):
        inputs[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    for relative, digest in inputs.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    queries = artifacts["queries.json"]
    train = read_json(ROOT / design["baseline"]["training_split"])["train"]
    checkpoints = {str(item["seed"]): KGECheckpoint.load(bound_file(ROOT, item))
                   for item in design["model"]["checkpoints"]}
    ranks, summary = calculate(design, queries, train, checkpoints)

    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "thu_hang.json", ranks)
    write_json(output / "chi_so.json", summary)
    checked = verify_scores(design["candidates"], queries, train, checkpoints,
                            read_json(output / "thu_hang.json"), read_json(output / "chi_so.json"))
    write_json(output / "kiem_chung.json", checked)
    plot(output / "doi_chung_t01.png", summary)
    for relative, digest in inputs.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    commit, dirty = get_git_info(ROOT)
    manifest = {
        "experiment_id": output.name, "protocol_version": parent["protocol_version"], "seed": None,
        "model_seeds": list(SEEDS), "stage": "retrospective_dev_scoring", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty}, "inputs": {**parent["inputs"], "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name, "authorization": "Yêu cầu chấm đối chứng hồi cứu của người dùng"},
        "artifacts": {"hashes": {p.name: sha256_file(p) for p in output.iterdir() if p.is_file()}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json_bytes(summary).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
