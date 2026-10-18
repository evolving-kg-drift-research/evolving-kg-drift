# Kế Hoạch Cải Thiện Chất Lượng Data — Không Dừng, Không Ngắt

> [!IMPORTANT]
> **Mục tiêu:** Data sau khi sửa phải sạch để train TransE đo drift chính xác.
> **7 bước tuần tự**, mỗi bước tự đủ — không phụ thuộc Neo4j, không chờ duyệt.
> **Tổng: ~2 ngày làm việc.**

---

## Bước 1 — Deduplicate snapshot export (3 giờ)

**Vấn đề:** Mỗi snapshot chứa support rows (cùng triple, khác source). T10 có 598/1803 rows lặp (33%). Tỷ lệ lặp tăng theo thời gian → tạo **drift giả** khi train TransE.

**File sửa:** [`src/07_run_bitemporal_snapshots.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/07_run_bitemporal_snapshots.py)

**Cách sửa:** Sau khi build snapshot, tách thành 2 output:
```python
# 1. Canonical triples (dùng cho TransE) — deduplicated
canonical = df.drop_duplicates(subset=["subject_id", "relation_id", "object_id"])
write_parquet(snapshots_dir / f"snapshot_{snap_id}_canonical.parquet", canonical)

# 2. Full provenance (giữ nguyên để truy vết) — giữ file cũ không đổi
write_parquet(snapshots_dir / f"snapshot_{snap_id}.parquet", df)  # Giữ nguyên
```

**Cập nhật config:** [`downstream_transe_config.yaml`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/runs/production_v2/config/downstream_transe_config.yaml) trỏ `parquet_path` sang file `_canonical`.

**Kết quả sau bước 1:**

| Snapshot | Rows cũ | Rows canonical | Loại bỏ |
|---|---:|---:|---:|
| T01 | 127 | 121 | 6 |
| T05 | 683 | 604 | 79 |
| T10 | 1803 | 1205 | 598 |

**Ảnh hưởng drift:** ✅ Trực tiếp — loại drift giả do trọng số training không đều.

---

## Bước 2 — Fix snapshot temporal ordering (2 giờ)

**Vấn đề:** Supersession xử lý trước validity filter. Nếu có correction tương lai sẽ xóa nhầm fact cũ đang hợp lệ.

**File sửa:** [`src/temporal/snapshot.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/temporal/snapshot.py) lines 29–66

**Diff:**
```diff
     for lfid, versions in logical_groups.items():
-        # 2. Resolve supersession chains.
-        superseded_by: dict[str, str] = {}
-        version_map = {v.fact_version_id: v for v in versions}
-        for v in versions:
-            if v.supersedes_version_id and v.supersedes_version_id in version_map:
-                existing_winner_id = superseded_by.get(v.supersedes_version_id)
-                if not existing_winner_id:
-                    superseded_by[v.supersedes_version_id] = v.fact_version_id
-                else:
-                    existing = version_map[existing_winner_id]
-                    if (v.evidence_observed_at, v.fact_version_id) > (existing.evidence_observed_at, existing.fact_version_id):
-                        superseded_by[v.supersedes_version_id] = v.fact_version_id
-        active_versions = []
-        winning_supersessions = set(superseded_by.values())
-        for v in versions:
-            current_id = v.fact_version_id
-            is_superseded = current_id in superseded_by
-            lost_tiebreaker = (v.supersedes_version_id is not None) and (current_id not in winning_supersessions)
-            if not is_superseded and not lost_tiebreaker:
-                active_versions.append(v)
-
-        # 3. Filter by validity and retraction
-        for v in active_versions:
-            if v.revision_type == "retraction":
-                continue
-            if v.valid_from <= cutoff:
-                if v.valid_to is None or cutoff < v.valid_to:
-                    resolved_facts.append(v)
+        # 2. Validity filter FIRST
+        valid_versions = [
+            v for v in versions
+            if v.valid_from <= cutoff and (v.valid_to is None or cutoff < v.valid_to)
+        ]
+
+        # 3. Retraction filter
+        non_retracted = [v for v in valid_versions if v.revision_type != "retraction"]
+
+        # 4. Supersession LAST — only among valid, non-retracted facts
+        version_map = {v.fact_version_id: v for v in non_retracted}
+        superseded_by: dict[str, str] = {}
+        for v in non_retracted:
+            if v.supersedes_version_id and v.supersedes_version_id in version_map:
+                existing_winner_id = superseded_by.get(v.supersedes_version_id)
+                if not existing_winner_id:
+                    superseded_by[v.supersedes_version_id] = v.fact_version_id
+                else:
+                    existing = version_map[existing_winner_id]
+                    if (v.evidence_observed_at, v.fact_version_id) > (existing.evidence_observed_at, existing.fact_version_id):
+                        superseded_by[v.supersedes_version_id] = v.fact_version_id
+        winning_supersessions = set(superseded_by.values())
+        for v in non_retracted:
+            current_id = v.fact_version_id
+            is_superseded = current_id in superseded_by
+            lost_tiebreaker = (v.supersedes_version_id is not None) and (current_id not in winning_supersessions)
+            if not is_superseded and not lost_tiebreaker:
+                resolved_facts.append(v)
```

**Test thêm vào:** [`tests/temporal/test_snapshot.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/tests/temporal/test_snapshot.py)
```python
def test_future_effective_correction_keeps_old_fact():
    """Correction đã biết nhưng chưa hiệu lực → fact cũ vẫn hiện."""
    old = FactVersion("fv1", "lf1", "A", "REL", "B",
        valid_from=dt(2020,1,1), valid_to=None,
        evidence_observed_at=dt(2020,1,1), ingested_at_real=dt(2020,1,1),
        supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h")
    correction = FactVersion("fv2", "lf1", "A", "REL", "C",
        valid_from=dt(2022,1,1), valid_to=None,  # Hiệu lực tương lai
        evidence_observed_at=dt(2021,1,1), ingested_at_real=dt(2021,1,1),
        supersedes_version_id="fv1", revision_type="correction",
        source_id="s1", source_url="", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h")

    snap, _ = build_snapshot([old, correction], cutoff=dt(2021,6,1))
    assert len(snap) == 1
    assert snap[0].fact_version_id == "fv1"  # Fact cũ vẫn hiện vì correction chưa valid
```

**Ảnh hưởng data hiện tại:** Không (data chỉ có `creation`). Nhưng đảm bảo pipeline đúng cho tương lai.

---

## Bước 3 — Quality gate fail-closed (30 phút)

**Vấn đề:** `evaluate_quality` trả PASS khi 0 facts khớp gold → 0/0 = error_rate 0.0 = PASS.

**File sửa:** [`src/kg_pipeline/quality.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/kg_pipeline/quality.py) line 45

**Diff:**
```diff
     error_rate = len(errors) / evaluated if evaluated > 0 else 0.0
-
-    return {
-        "status": "PASS" if error_rate <= error_threshold else "FAIL",
+    if evaluated == 0:
+        return {
+            "status": "FAIL",
+            "reason": "ZERO_COVERAGE",
+            "evaluated_count": 0,
+            "error_count": 0,
+            "error_rate": None,
+            "errors": []
+        }
+    return {
+        "status": "PASS" if error_rate <= error_threshold else "FAIL",
```

**Ảnh hưởng:** Report trung thực — không claim quality PASS khi chưa kiểm.

---

## Bước 4 — Loại bỏ auto-trust và timestamp clamping (1.5 giờ)

**Vấn đề 1:** `bodyvariant_` prefix → auto-accept, confidence 0.9 không qua kiểm chứng.
**Vấn đề 2:** `valid_from > observed_at` → clamp về `observed_at`, mất thông tin future-effective.

**File sửa:** [`src/kg_pipeline/adjudication.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/kg_pipeline/adjudication.py)

**Diff 1 — Bỏ auto-trust (line 101-102):**
```diff
-        is_trusted = claim.source_id in WHITELIST_SOURCES or claim.source_id.startswith("bodyvariant_")
-        confidence = 0.9 if is_trusted else 0.5
+        is_trusted = claim.source_id in WHITELIST_SOURCES
+        confidence = 0.85 if is_trusted else 0.5
```

> [!NOTE]
> Không dùng 0.9 để tránh nhầm với "đã kiểm chứng". 0.85 cho whitelist sources, 0.5 cho phần còn lại. Cả hai đều là heuristic, nhưng pipeline hiện tại accept tất cả `bodyvariant_` sources nên thay đổi này không ảnh hưởng data output — chỉ ghi nhận trung thực hơn.

**Diff 2 — Bỏ clamping (line 82-86):**
```diff
-        if valid_from > observed_at:
-            valid_from = observed_at
-
-        if valid_to and valid_to > observed_at:
-            valid_to = observed_at
+        # Ghi provenance thay vì clamp — future-effective facts là data hợp lệ
+        # valid_from > observed_at chỉ nghĩa là "sự kiện sẽ xảy ra từ ngày X"
```

**File sửa 2:** [`src/kg_pipeline/adjudicate.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/kg_pipeline/adjudicate.py) line 90, 110

**Diff — Observation time fallback (line 88-90):**
```diff
         if doc_time_str:
             observation_times[claim.claim_id] = datetime.fromisoformat(doc_time_str)
         else:
-            observation_times[claim.claim_id] = now_utc
+            # Fallback: dùng wall clock nhưng ghi rõ provenance
+            observation_times[claim.claim_id] = now_utc  # TODO: flag as FALLBACK_WALL_CLOCK
```

**Ảnh hưởng data:** Không đổi data output trực tiếp vì pipeline đã chạy xong — chỉ ảnh hưởng nếu rebuild từ claims.

---

## Bước 5 — Neo4j parity report trung thực (45 phút)

**Vấn đề:** Script so Parquet với chính nó nhưng report ghi "Neo4j Bolt Query Layer PASS".

**File sửa:** [`src/08_run_canonical_neo4j_parity.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/src/08_run_canonical_neo4j_parity.py) line 180, 183–188

**Diff:**
```diff
-        "materialization_layer": "Neo4j CSV & Bolt Query Layer",
+        "materialization_layer": "Neo4j CSV Export (no database read-back)",
         ...
         "hard_invariants": {
             "SET_EQUALITY": True,
             "ROW_COUNTS_MATCH": True,
             "ENTITY_COUNTS_MATCH": True,
             "RELATION_COUNTS_MATCH": True,
             "ZERO_MANUAL_NEO4J_PATCH": True,
+            "DB_READ_BACK_PERFORMED": False,
         },
```

**Ảnh hưởng:** Report trung thực. Không ảnh hưởng data.

---

## Bước 6 — Regression tests (2 giờ)

**Vấn đề:** 3 file test rỗng (0 bytes).

| File | Viết test gì |
|---|---|
| [`tests/test_entity_mapping.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/tests/test_entity_mapping.py) | `fuzzy_match_entity`: exact match, case-insensitive, substring, None khi không tìm thấy |
| [`tests/test_fact_schema.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/tests/test_fact_schema.py) | `FactVersion` timezone enforcement, span validation, valid_from < valid_to |
| [`tests/test_protocol.py`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/tests/test_protocol.py) | Protocol YAML readable, decision log parseable, source lock file exists |

---

## Bước 7 — Cleanup + rebuild (2 giờ)

**7a. Xóa credential (5 phút):**
[`docs/PROGRESS.md`](file:///d:/Học%20tập%20kì%201/Học%20máy%20nâng%20cao%20Nguyễn%20Đình%20Quý/PJ_B1/evolving-kg-drift/docs/PROGRESS.md) line 135: thay `sk-1ad27e92...` bằng `<REDACTED>`.

**7b. Rebuild `production_v3` (1.5 giờ):**
Chạy lại Stage 4.16 → 4.17 → 4.18 với code đã sửa, tạo run mới. Giữ `production_v2` nguyên.

**7c. Cập nhật `downstream_transe_config.yaml` (15 phút):**
Trỏ sang canonical snapshots mới, ghi `unique_edges` thay vì `edges` (row count).

**7d. Chạy test suite (15 phút):**
```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

---

## Tổng kết

| Bước | File chính | Thời gian | Thay đổi data? | Blockers |
|---|---|---:|---|---|
| 1. Dedup support rows | `07_run_bitemporal_snapshots.py` | 3h | ✅ **Có** | Không |
| 2. Temporal ordering | `temporal/snapshot.py` | 2h | Future-proof | Không |
| 3. Quality gate | `quality.py` | 30m | Report only | Không |
| 4. Auto-trust + clamp | `adjudication.py` | 1.5h | Nếu rebuild | Không |
| 5. Neo4j report | `08_run_canonical_neo4j_parity.py` | 45m | Report only | Không |
| 6. Empty tests | 3 test files | 2h | Không | Không |
| 7. Cleanup + rebuild | PROGRESS.md + pipeline | 2h | ✅ **Có** | Không |
| **Tổng** | | **~12h** | | **0 blockers** |

> [!TIP]
> **Không có bước nào cần chờ quyết định bên ngoài.** Mọi quyết định khoa học đã được nhúng sẵn:
> - Clock basis: dùng `evidence_observed_at` hiện có (đã gán từ retrieval/archive time)
> - Support rows: giữ file gốc + thêm file `_canonical` deduplicated
> - Quality threshold: fail-closed (0 coverage = FAIL)
