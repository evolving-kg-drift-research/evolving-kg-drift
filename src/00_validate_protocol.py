"""
src/00_lock_protocol.py
Bước 1 (Mục 4.1) - Khóa hợp đồng nghiên cứu và hard invariants.
Domain: AI và Công nghệ.

Chạy từ thư mục gốc repo (evolving-ai-kg/):
    pip install -r requirement.txt
    python src/00_lock_protocol.py

Sinh ra:
    config/protocol.yaml
    docs/data_contract.md
    data/manifests/pipeline_versions.json
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml  # pip install pyyaml

# Chạy script này từ thư mục gốc repo, nên các path là tương đối gốc repo
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DOCS_DIR = REPO_ROOT / "docs"
MANIFEST_DIR = REPO_ROOT / "data" / "manifests"
for d in (CONFIG_DIR, DOCS_DIR, MANIFEST_DIR):
    d.mkdir(parents=True, exist_ok=True)

PROTOCOL = {
    "protocol_version": "0.1.0",
    "data_contract_version": "0.1.0",
    "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "domain_scope": {
        "domain_name": "AI và Công nghệ",
        "description": (
            "Miền hẹp tập trung vào tin tức, sự kiện, sản phẩm và nghiên cứu "
            "liên quan đến trí tuệ nhân tạo (AI) và công nghệ nói chung."
        ),
        "note": (
            "Chọn domain 'AI và công nghệ' là quyết định triển khai của nhóm, "
            "không phải tên miền bắt buộc từ đề cương D1."
        ),
    },
    "hard_invariants": [
        {"id": "INV-01", "name": "no_future_evidence",
         "impl": "src/invariants.py::no_future_evidence",
         "description": "Không dùng evidence có evidence_observed_at > cutoff của snapshot."},
        {"id": "INV-02", "name": "no_future_entity_mapping",
         "impl": "src/invariants.py::no_future_entity_mapping",
         "description": "Không dùng entity mapping có available_at > known_at."},
        {"id": "INV-03", "name": "append_only_provenance",
         "impl": "src/invariants.py::is_append_only",
         "description": "Raw data & provenance chỉ được thêm mới, không sửa/xóa/ghi đè."},
        {"id": "INV-04", "name": "deterministic_rebuild",
         "impl": "src/invariants.py::is_deterministic",
         "description": "Cùng input+config+mapping version phải tái tạo cùng output (cùng hash)."},
        {"id": "INV-05", "name": "parquet_neo4j_set_equality",
         "impl": "src/invariants.py::is_set_equal",
         "description": "Tập entity/relation trong Parquet và Neo4j của cùng snapshot phải bằng nhau."},
        {"id": "INV-06", "name": "no_outcome_tuning",
         "impl": "src/invariants.py::no_outcome_tuning",
         "description": "Không dùng đặc trưng downstream (sed_plus, rr_score...) để lọc/chọn dữ liệu."},
    ],
    "time_field_roles": {
        "valid_from": {"axis": "valid_at", "meaning": "Thời điểm fact bắt đầu hiệu lực trong thực tế."},
        "valid_to": {"axis": "valid_at", "meaning": "Thời điểm fact hết hiệu lực (nếu có)."},
        "evidence_observed_at": {"axis": "known_at", "meaning": "Thời điểm evidence trở nên công khai."},
        "accepted_into_kg_at": {"axis": "known_at", "meaning": "Thời điểm sớm nhất evidence đủ để chấp nhận fact."},
        "retrieved_at_real": {"axis": "project_time", "meaning": "Thời điểm dự án crawl thực tế (chỉ provenance)."},
        "adjudicated_at_real": {"axis": "project_time", "meaning": "Thời điểm review thực tế (chỉ provenance)."},
    },
    "mutable_after_pilot_without_reprocess": [
        "comment/label không ảnh hưởng ngữ nghĩa",
        "mô tả nội bộ của relation",
    ],
    "must_reprocess_full_corpus_if_changed": [
        "ontology.yaml (relation semantics/cardinality)",
        "logical_fact_id_rule",
        "extractor_version (dùng trong 05_extract_candidates.py)",
        "entity_map_version (dùng trong 09_resolve_entities.py)",
        "adjudication_rule_version (dùng trong 08_adjudicate.py)",
        "snapshot_builder_version (dùng trong 11_build_snapshots.py)",
    ],
}

DATA_CONTRACT_MD = """# Data Contract - Bước 1 (Mục 4.1)

**protocol_version:** {protocol_version}
**Domain:** AI và Công nghệ

## Phạm vi dữ liệu
- Quy mô khởi đầu: 600-900 bài, 8-10 loại quan hệ, 8-12 lát cắt (ước lượng, không phải quota cứng).
- Pilot: 30-50 bài, 3 tiny snapshots.

## 6 hard invariants (xem chi tiết + code trong config/protocol.yaml và src/invariants.py)
INV-01 no_future_evidence · INV-02 no_future_entity_mapping · INV-03 append_only_provenance ·
INV-04 deterministic_rebuild · INV-05 parquet_neo4j_set_equality · INV-06 no_outcome_tuning

## Trục thời gian bắt buộc phân biệt
| Trục | Trường | Dùng ở script |
|---|---|---|
| valid_at | valid_from / valid_to | 10_build_fact_versions.py |
| known_at | evidence_observed_at | 10_build_fact_versions.py |
| known_at | accepted_into_kg_at | 08_adjudicate.py |
| project_time | retrieved_at_real | 02_fetch_articles.py |
| project_time | adjudicated_at_real | 08_adjudicate.py |

## Điều kiện Pass Bước 1
Mọi trường thời gian có định nghĩa không mâu thuẫn; test khung ở
tests/test_no_future_leakage.py, tests/test_parquet_neo4j_parity.py,
tests/test_no_duplicate_sources.py, tests/test_deterministic_rebuild.py,
tests/test_no_outcome_tuning.py đã được viết (chưa cần data thật).
""".format(protocol_version=PROTOCOL["protocol_version"])


def write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


if __name__ == "__main__":
    protocol_path = CONFIG_DIR / "protocol.yaml"
    write_yaml(protocol_path, PROTOCOL)
    print(f"[OK] {protocol_path}")

    contract_path = DOCS_DIR / "data_contract.md"
    contract_path.write_text(DATA_CONTRACT_MD, encoding="utf-8")
    print(f"[OK] {contract_path}")

    protocol_hash = sha256_of_file(protocol_path)
    manifest = {
        "manifest_version": "1.0",
        "protocol_version": PROTOCOL["protocol_version"],
        "data_contract_version": PROTOCOL["data_contract_version"],
        "ontology_version": None,          # điền ở Bước 7 (pilot)
        "extractor_version": None,         # điền ở Bước 9
        "entity_map_version": None,        # điền ở Bước 8
        "adjudication_rule_version": None, # điền ở Bước 11
        "snapshot_builder_version": None,  # điền ở giai đoạn build snapshot
        "created_at_real": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash,
    }
    manifest_path = MANIFEST_DIR / "pipeline_versions.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {manifest_path}")
    print(f"[HASH] protocol.yaml sha256 = {protocol_hash}")
    print("=> Copy hash này vào README.md, coi đây là bằng chứng 'ngày khóa protocol'.")