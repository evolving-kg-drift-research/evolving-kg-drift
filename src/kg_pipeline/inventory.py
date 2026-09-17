"""Ticket A raw inventory, evidence recovery, body extraction, and exact deduplication."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .contracts import make_row
from .hashing import (
    canonical_json,
    repo_relative,
    sha256_file,
    sha256_json,
    sha256_text,
    stable_id,
    utc_now_iso,
)
from .reconcile import reconcile_stage_4_3
from .run import (
    get_run_dir,
    inspect_source_lock,
    load_run_manifest,
    package_fingerprint,
)
from .storage import (
    append_jsonl,
    read_json,
    read_yaml,
    write_json_immutable,
    write_parquet_immutable,
    write_text_cas,
)

RAW_SCOPE_RELATIVE = Path("data/raw/stage_4_4")
BLOB_SCOPE_RELATIVE = RAW_SCOPE_RELATIVE / "blobs" / "sha256"
PARSER_VERSION = "html_body_extract_v1"
HASH_FIELDS = {"payload_sha256", "raw_payload_sha256", "content_hash_sha256", "blob_sha256", "sha256"}
EVIDENCE_ROOTS = (
    Path("data/stage_4_3_runs"),
    Path("data/stage_4_4_runs"),
    Path("data/manifests"),
    Path("reports"),
    Path("logs"),
)


def _package_parser_fingerprint() -> str:
    return sha256_file(Path(__file__))


def _sorted_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.as_posix())


def _filename_hash(path: Path) -> tuple[str | None, str]:
    candidate = path.stem.lower()
    if re.fullmatch(r"[0-9a-f]{64}", candidate):
        return candidate, "UNVERIFIED_FILENAME_CLAIM"
    return None, "NOT_HASH_NAMED"


def _sniff_content_type(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        header = handle.read(16384)
    trimmed = header.lstrip().lower()
    if b"<!doctype html" in trimmed[:1024] or b"<html" in trimmed[:4096]:
        return "text/html", "magic_html_prefix"
    if trimmed.startswith(b"<?xml"):
        return "application/xml", "magic_xml_prefix"
    if trimmed.startswith((b"{", b"[")):
        return "application/json", "magic_json_prefix"
    if b"\x00" not in header:
        try:
            header.decode("utf-8")
            return "text/plain", "utf8_probe"
        except UnicodeDecodeError:
            pass
    return "application/octet-stream", "binary_probe"


def _decode_raw(raw_bytes: bytes) -> tuple[str, str, list[str]]:
    """Decode bytes conservatively and record every non-default fallback."""

    head = raw_bytes[:8192].decode("latin-1", errors="ignore")
    declared = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9_\-]+)", head, flags=re.IGNORECASE)
    candidates = [declared.group(1)] if declared else []
    candidates.extend(["utf-8", "utf-8-sig", "windows-1258", "latin-1"])
    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            text = raw_bytes.decode(encoding)
            flags = [] if normalized in {"utf-8", "utf-8-sig"} else [f"DECODE_FALLBACK_{normalized.upper()}"]
            return text, encoding, flags
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_bytes.decode("utf-8", errors="replace"), "utf-8-replace", ["DECODE_REPLACEMENT"]


def extract_body(path: Path, content_type: str) -> dict[str, Any]:
    """Extract text only; this function makes no scope, time, or quality decision."""

    if not content_type.startswith("text/"):
        return {
            "extraction_status": "NOT_APPLICABLE_NON_TEXT",
            "body_text": None,
            "decoder": None,
            "selector": None,
            "quality_flags": ["NON_TEXT_RAW"],
        }
    try:
        raw_bytes = path.read_bytes()
        document, decoder, flags = _decode_raw(raw_bytes)
        if content_type == "text/plain":
            body_text = re.sub(r"\s+", " ", document.replace("\u00a0", " ")).strip()
            selector = "raw_text"
        else:
            soup = BeautifulSoup(document, "html.parser")
            for node in soup(["script", "style", "noscript", "template", "svg", "iframe", "form", "button", "nav", "footer", "aside", "header"]):
                node.decompose()
            candidates: tuple[tuple[str, str], ...] = (
                ("article", "article"),
                ("article_body", "[class*='article-body'], [class*='article__body'], [class*='content-detail']"),
                ("main", "main"),
                ("body", "body"),
            )
            target = None
            selector = None
            for label, expression in candidates:
                target = soup.select_one(expression)
                if target is not None:
                    selector = label
                    break
            if target is None:
                return {
                    "extraction_status": "PARSER_NO_BODY_NODE",
                    "body_text": None,
                    "decoder": decoder,
                    "selector": None,
                    "quality_flags": sorted(flags + ["PARSER_NO_BODY_NODE"]),
                }
            body_text = re.sub(r"\s+", " ", target.get_text(" ", strip=True).replace("\u00a0", " ")).strip()
            if selector == "body":
                flags.append("PARSER_FALLBACK_BODY")
        if not body_text:
            return {
                "extraction_status": "EMPTY_BODY",
                "body_text": None,
                "decoder": decoder,
                "selector": selector,
                "quality_flags": sorted(flags + ["EMPTY_BODY"]),
            }
        if len(body_text) < 200:
            flags.append("SHORT_BODY_LT_200_CHARS")
        return {
            "extraction_status": "EXTRACTED",
            "body_text": body_text,
            "decoder": decoder,
            "selector": selector,
            "quality_flags": sorted(flags + ["BODY_EXTRACTED"]),
        }
    except Exception as exc:  # noqa: BLE001 - content remains in the raw inventory even if parser fails
        return {
            "extraction_status": "PARSER_ERROR",
            "body_text": None,
            "decoder": None,
            "selector": None,
            "quality_flags": ["PARSER_ERROR", type(exc).__name__],
        }


def _evidence_files(repo_root: Path) -> list[Path]:
    paths: set[Path] = set()
    for relative in EVIDENCE_ROOTS:
        root = repo_root / relative
        if root.is_dir():
            paths.update(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".jsonl"})
    return sorted(paths, key=lambda path: repo_relative(path, repo_root))


def _iter_json_records(payload: Any, locator: str = "$") -> Iterable[tuple[dict[str, Any], str]]:
    if isinstance(payload, dict):
        yield payload, locator
        for key, value in payload.items():
            yield from _iter_json_records(value, f"{locator}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _iter_json_records(value, f"{locator}[{index}]")


def _matched_hashes(record: dict[str, Any], raw_hashes: set[str]) -> set[str]:
    matches = set()
    for key, value in record.items():
        if key.lower() in HASH_FIELDS and isinstance(value, str) and value.lower() in raw_hashes:
            matches.add(value.lower())
    return matches


def _first_string(record: dict[str, Any], *names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = record.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip(), name
    return None, None


def _recovery_row(
    raw_blob_sha256: str,
    record: dict[str, Any],
    evidence_path: str,
    evidence_locator: str,
    evidence_file_sha256: str,
) -> dict[str, Any]:
    source_id, _ = _first_string(record, "source_id")
    requested_url, _ = _first_string(record, "requested_url", "url", "archive_uri")
    final_url, _ = _first_string(record, "final_url")
    retrieved_at_real, _ = _first_string(record, "retrieved_at_real")
    archive_datetime, _ = _first_string(record, "archive_datetime", "archive_or_revision_datetime")
    recorded_event_at, recorded_event_time_field = _first_string(
        record, "retrieved_at_real", "ingested_at_real", "discovered_at_real", "event_at_real"
    )
    evidence_record_sha256 = sha256_json(record)
    record_identifier, _ = _first_string(record, "retrieval_id", "event_id", "request_id", "acquisition_event_id")
    retrieval_id = stable_id(
        "retrieval",
        {
            "raw_blob_sha256": raw_blob_sha256,
            "evidence_path": evidence_path,
            "evidence_locator": evidence_locator,
            "record_identifier": record_identifier,
            "record_sha256": evidence_record_sha256,
        },
    )
    strict = bool(source_id and final_url and retrieved_at_real)
    if strict:
        provenance_status = "VERIFIED_ACQUISITION_EVIDENCE"
    elif source_id and (requested_url or final_url):
        provenance_status = "PARTIAL_ACQUISITION_EVIDENCE_TIME_UNKNOWN"
    else:
        provenance_status = "HASH_MATCHED_EVIDENCE_METADATA_PARTIAL"
    return make_row(
        "retrievals",
        retrieval_id=retrieval_id,
        raw_blob_sha256=raw_blob_sha256,
        source_id=source_id,
        requested_url=requested_url,
        final_url=final_url,
        retrieved_at_real=retrieved_at_real,
        archive_datetime=archive_datetime,
        recorded_event_at=recorded_event_at,
        recorded_event_time_field=recorded_event_time_field,
        provenance_status=provenance_status,
        strict_source_input_eligible=strict,
        evidence_path=evidence_path,
        evidence_locator=evidence_locator,
        evidence_file_sha256=evidence_file_sha256,
        evidence_record_sha256=evidence_record_sha256,
    )


def scan_acquisition_evidence(repo_root: Path, raw_hashes: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Recover only direct hash-linked evidence; mtime and page metadata are never consulted."""

    recoveries: list[dict[str, Any]] = []
    scan_errors: list[str] = []
    for path in _evidence_files(repo_root):
        relative = repo_relative(path, repo_root)
        try:
            evidence_sha256 = sha256_file(path)
            if path.suffix.lower() == ".jsonl":
                with path.open("r", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict):
                            continue
                        for raw_hash in sorted(_matched_hashes(record, raw_hashes)):
                            recoveries.append(_recovery_row(raw_hash, record, relative, f"line:{line_number}", evidence_sha256))
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                for record, locator in _iter_json_records(payload):
                    for raw_hash in sorted(_matched_hashes(record, raw_hashes)):
                        recoveries.append(_recovery_row(raw_hash, record, relative, locator, evidence_sha256))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            scan_errors.append(f"{relative}: {type(exc).__name__}: {exc}")
    recoveries.sort(key=lambda row: (row["raw_blob_sha256"], row["evidence_path"], row["evidence_locator"], row["retrieval_id"]))
    return recoveries, scan_errors


def _artifact_semantic_hash(run_dir: Path, stem: str) -> str | None:
    manifest_path = run_dir / "tables" / f"{stem}.parquet.manifest.json"
    return read_json(manifest_path).get("semantic_sha256") if manifest_path.is_file() else None


def _stage_4_3_summary(run_dir: Path) -> dict[str, Any]:
    report_path = run_dir / "reports" / "stage_4_3_reconciliation.json"
    if not report_path.is_file():
        return {"status": "NOT_RUN", "counts": {}}
    return read_json(report_path)


def run_inventory(repo_root: Path, run_id: str, *, verify_inputs: bool) -> dict[str, Any]:
    """Create a fresh immutable Ticket A inventory without changing raw or upstream artifacts."""

    load_run_manifest(repo_root, run_id)
    run_dir = get_run_dir(repo_root, run_id)
    if verify_inputs:
        reconcile_stage_4_3(repo_root, run_id)
    stage_4_3 = _stage_4_3_summary(run_dir)
    raw_scope = repo_root / RAW_SCOPE_RELATIVE
    raw_files = _sorted_files(raw_scope)
    raw_infos: list[dict[str, Any]] = []
    for path in raw_files:
        relative = repo_relative(path, repo_root)
        raw_kind = "RAW_BLOB" if path.is_relative_to(repo_root / BLOB_SCOPE_RELATIVE) else "RAW_AUXILIARY"
        filename_sha256, filename_status = _filename_hash(path)
        try:
            current_hash = sha256_file(path)
            if filename_sha256:
                filename_status = "MATCH" if filename_sha256 == current_hash else "MISMATCH"
            content_type, content_type_basis = _sniff_content_type(path)
            read_status = "OK"
            read_error = None
        except OSError as exc:
            current_hash = None
            content_type = None
            content_type_basis = None
            read_status = "READ_ERROR"
            read_error = f"{type(exc).__name__}: {exc}"
        raw_candidate_id = stable_id("raw", {"relative_path": relative})
        raw_infos.append(
            {
                "path": path,
                "relative_path": relative,
                "raw_kind": raw_kind,
                "raw_candidate_id": raw_candidate_id,
                "raw_blob_sha256": current_hash,
                "filename_sha256": filename_sha256,
                "filename_hash_status": filename_status,
                "bytes": path.stat().st_size if read_status == "OK" else None,
                "content_type_detected": content_type,
                "content_type_basis": content_type_basis,
                "read_status": read_status,
                "read_error": read_error,
            }
        )
    raw_hashes = {info["raw_blob_sha256"] for info in raw_infos if info["raw_blob_sha256"]}
    recovery_rows, recovery_scan_errors = scan_acquisition_evidence(repo_root, raw_hashes)
    recoveries_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recovery_rows:
        recoveries_by_hash[row["raw_blob_sha256"]].append(row)

    raw_inventory_rows: list[dict[str, Any]] = []
    hash_audit_rows: list[dict[str, Any]] = []
    source_version_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for info in raw_infos:
        raw_hash = info["raw_blob_sha256"]
        recoveries = recoveries_by_hash.get(raw_hash, []) if raw_hash else []
        strict_from_evidence = any(row["strict_source_input_eligible"] for row in recoveries)
        historical_hash_status = "VERIFIED_AGAINST_ACQUISITION_EVIDENCE" if recoveries else "NO_HISTORICAL_HASH_EVIDENCE"
        if info["read_status"] != "OK":
            source_status = "ERROR_UNREADABLE_RAW"
            strict = False
            unknown_reason = "Byte read failed; hash and provenance cannot be verified"
        elif strict_from_evidence and info["filename_hash_status"] == "MATCH":
            source_status = "VERIFIED_ACQUISITION_EVIDENCE"
            strict = True
            unknown_reason = None
        elif recoveries:
            source_status = "PARTIAL_ACQUISITION_EVIDENCE"
            strict = False
            unknown_reason = "Evidence record is hash-linked but lacks a required acquisition field"
        else:
            source_status = "UNRESOLVED_NO_ACQUISITION_EVIDENCE"
            strict = False
            unknown_reason = "No direct hash-linked acquisition record was found in allowed evidence roots"
        raw_inventory_rows.append(
            make_row(
                "raw_inventory",
                inventory_row_id=stable_id("inventory", {"raw_candidate_id": info["raw_candidate_id"]}),
                raw_candidate_id=info["raw_candidate_id"],
                raw_kind=info["raw_kind"],
                relative_path=info["relative_path"],
                raw_blob_sha256=raw_hash,
                filename_sha256=info["filename_sha256"],
                filename_hash_status=info["filename_hash_status"],
                bytes=info["bytes"],
                content_type_detected=info["content_type_detected"],
                content_type_basis=info["content_type_basis"],
                read_status=info["read_status"],
                read_error=info["read_error"],
                hash_computed_now=info["read_status"] == "OK",
                historical_hash_evidence_status=historical_hash_status,
                historical_hash_evidence_count=len(recoveries),
                source_provenance_status=source_status,
                strict_input_eligible=strict,
                unknown_reason=unknown_reason,
            )
        )
        hash_audit_rows.append(
            make_row(
                "raw_hash_audit",
                hash_audit_id=stable_id("hashaudit", {"raw_candidate_id": info["raw_candidate_id"]}),
                raw_candidate_id=info["raw_candidate_id"],
                relative_path=info["relative_path"],
                bytes=info["bytes"],
                computed_sha256=raw_hash,
                hash_computed_now=info["read_status"] == "OK",
                filename_sha256=info["filename_sha256"],
                filename_hash_status=info["filename_hash_status"],
                historical_hash_evidence_status=historical_hash_status,
                historical_hash_evidence_count=len(recoveries),
                read_status=info["read_status"],
                read_error=info["read_error"],
            )
        )
        if raw_hash:
            provenance_rows.append(
                make_row(
                    "provenance_recovery_ledger",
                    ledger_id=stable_id("provenance", {"raw": raw_hash, "field": "raw_blob_sha256", "path": info["relative_path"]}),
                    raw_blob_sha256=raw_hash,
                    field_name="raw_blob_sha256",
                    recovered_value=raw_hash,
                    recovery_status="COMPUTED_NOW_NOT_HISTORICAL_PROOF",
                    reason="SHA-256 was recomputed from bytes present during Ticket A inventory",
                    evidence_path=info["relative_path"],
                    evidence_locator="bytes:0-end",
                    evidence_file_sha256=raw_hash,
                )
            )
        if not recoveries:
            missing_rows.append(
                make_row(
                    "missing_coverage_ledger",
                    issue_id=stable_id("issue", {"raw_candidate_id": info["raw_candidate_id"], "kind": "acquisition_provenance"}),
                    issue_type="UNRESOLVED_ACQUISITION_PROVENANCE",
                    raw_candidate_id=info["raw_candidate_id"],
                    raw_blob_sha256=raw_hash,
                    severity="BLOCKER",
                    blocks_strict_input=True,
                    reason=unknown_reason,
                    recommended_next_action="Locate an immutable acquisition manifest/log with exact blob hash, source URL, and retrieved_at_real; do not infer from mtime or article metadata.",
                )
            )
        elif not strict:
            missing_rows.append(
                make_row(
                    "missing_coverage_ledger",
                    issue_id=stable_id("issue", {"raw_candidate_id": info["raw_candidate_id"], "kind": "partial_acquisition_provenance"}),
                    issue_type="PARTIAL_ACQUISITION_PROVENANCE",
                    raw_candidate_id=info["raw_candidate_id"],
                    raw_blob_sha256=raw_hash,
                    severity="BLOCKER",
                    blocks_strict_input=True,
                    reason=unknown_reason,
                    recommended_next_action="Recover the missing acquisition fields from a trusted manifest or log; leave unknown until then.",
                )
            )
        for retrieval in recoveries:
            source_version_id = stable_id(
                "sourceversion", {"raw_blob_sha256": retrieval["raw_blob_sha256"], "retrieval_id": retrieval["retrieval_id"]}
            )
            source_version_rows.append(
                make_row(
                    "source_versions",
                    source_version_id=source_version_id,
                    raw_blob_sha256=retrieval["raw_blob_sha256"],
                    retrieval_id=retrieval["retrieval_id"],
                    source_id=retrieval["source_id"],
                    canonical_or_final_url=retrieval["final_url"] or retrieval["requested_url"],
                    retrieved_at_real=retrieval["retrieved_at_real"],
                    archive_datetime=retrieval["archive_datetime"],
                    source_version_status=retrieval["provenance_status"],
                    strict_source_input_eligible=retrieval["strict_source_input_eligible"],
                    evidence_path=retrieval["evidence_path"],
                    evidence_locator=retrieval["evidence_locator"],
                )
            )
            for field_name in ("source_id", "requested_url", "final_url", "retrieved_at_real", "archive_datetime"):
                value = retrieval[field_name]
                provenance_rows.append(
                    make_row(
                        "provenance_recovery_ledger",
                        ledger_id=stable_id("provenance", {"retrieval": retrieval["retrieval_id"], "field": field_name}),
                        raw_blob_sha256=retrieval["raw_blob_sha256"],
                        field_name=field_name,
                        recovered_value=value,
                        recovery_status="RECOVERED" if value else "UNKNOWN",
                        reason=retrieval["provenance_status"],
                        evidence_path=retrieval["evidence_path"],
                        evidence_locator=retrieval["evidence_locator"],
                        evidence_file_sha256=retrieval["evidence_file_sha256"],
                    )
                )

    inventory_by_id = {row["raw_candidate_id"]: row for row in raw_inventory_rows}
    body_variant_rows_by_id: dict[str, dict[str, Any]] = {}
    memberships: list[dict[str, Any]] = []
    extraction_cache: dict[str, dict[str, Any]] = {}
    for info in raw_infos:
        inventory = inventory_by_id[info["raw_candidate_id"]]
        if info["raw_kind"] != "RAW_BLOB" or info["read_status"] != "OK":
            continue
        raw_hash = info["raw_blob_sha256"]
        if raw_hash not in extraction_cache:
            extraction_cache[raw_hash] = extract_body(info["path"], info["content_type_detected"])
        extraction = extraction_cache[raw_hash]
        body_variant_id = None
        exact_cluster_id = None
        if extraction["body_text"]:
            body_sha256 = sha256_text(extraction["body_text"])
            body_blob_path = run_dir / "body_blobs" / "sha256" / body_sha256[:2] / f"{body_sha256}.txt"
            write_text_cas(body_blob_path, extraction["body_text"], body_sha256)
            body_variant_id = stable_id(
                "bodyvariant", {"body_text_sha256": body_sha256, "parser_version": PARSER_VERSION, "parser_fingerprint": _package_parser_fingerprint()}
            )
            exact_cluster_id = stable_id("cluster", {"type": "EXACT_BODY_SHA256_V1", "body_text_sha256": body_sha256})
            body_variant_rows_by_id.setdefault(
                body_variant_id,
                make_row(
                    "body_variants",
                    body_variant_id=body_variant_id,
                    body_text_sha256=body_sha256,
                    body_blob_relative_path=repo_relative(body_blob_path, repo_root),
                    parser_version=PARSER_VERSION,
                    parser_fingerprint_sha256=_package_parser_fingerprint(),
                    decoder=extraction["decoder"],
                    selector=extraction["selector"],
                    text_char_count=len(extraction["body_text"]),
                    extraction_status=extraction["extraction_status"],
                    quality_flags_json=canonical_json(extraction["quality_flags"]),
                ),
            )
        else:
            missing_rows.append(
                make_row(
                    "missing_coverage_ledger",
                    issue_id=stable_id("issue", {"raw_candidate_id": info["raw_candidate_id"], "kind": extraction["extraction_status"]}),
                    issue_type="BODY_EXTRACTION_NOT_READY",
                    raw_candidate_id=info["raw_candidate_id"],
                    raw_blob_sha256=raw_hash,
                    severity="REVIEW",
                    blocks_strict_input=False,
                    reason=f"{extraction['extraction_status']}: {canonical_json(extraction['quality_flags'])}",
                    recommended_next_action="Review parser evidence without treating this as a corpus filter decision.",
                )
            )
        memberships.append(
            make_row(
                "document_memberships",
                membership_id=stable_id("membership", {"raw_candidate_id": info["raw_candidate_id"], "body_variant_id": body_variant_id}),
                raw_blob_sha256=raw_hash,
                raw_candidate_id=info["raw_candidate_id"],
                body_variant_id=body_variant_id,
                exact_cluster_id=exact_cluster_id,
                retrieval_ids_json=canonical_json([row["retrieval_id"] for row in recoveries_by_hash.get(raw_hash, [])]),
                source_provenance_status=inventory["source_provenance_status"],
                strict_input_eligible=inventory["strict_input_eligible"],
                membership_status="BODY_EXTRACTED" if body_variant_id else extraction["extraction_status"],
                reason="No content scope/filter decision was made in Ticket A.",
            )
        )

    members_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for membership in memberships:
        if membership["exact_cluster_id"]:
            members_by_cluster[membership["exact_cluster_id"]].append(membership)
    cluster_rows: list[dict[str, Any]] = []
    for cluster_id, members in sorted(members_by_cluster.items()):
        members.sort(key=lambda row: row["membership_id"])
        cluster_rows.append(
            make_row(
                "document_clusters",
                cluster_id=cluster_id,
                cluster_type="EXACT_BODY",
                body_variant_id=members[0]["body_variant_id"],
                member_count=len(members),
                member_ids_json=canonical_json([member["membership_id"] for member in members]),
                dedup_method="NORMALIZED_BODY_SHA256_V1",
                policy_status="IMPLEMENTED_EXACT_ONLY",
            )
        )

    near_duplicate_rows = [
        make_row(
            "near_duplicate_candidates",
            candidate_id=stable_id(
                "nearcandidate",
                {"policy": "EXACT_BODY_ONLY_STAGE_A_V1"},
            ),
            left_body_variant_id=None,
            right_body_variant_id=None,
            candidate_generation_status="NOT_RUN_BY_FROZEN_STAGE_A_POLICY",
            reason=(
                "ADR 0005 freezes Stage A at Exact-body CAS Deduplication. "
                "Near-duplicate/copy/lineage inference is intentionally deferred "
                "to a later stage; no pairwise inference was made."
            ),
            policy_status="VERSIONED_EXACT_ONLY_STAGE_A",
        )
    ]
    missing_rows.append(
        make_row(
            "missing_coverage_ledger",
            issue_id=stable_id(
                "issue",
                {"kind": "near_duplicate_policy_deferred"},
            ),
            issue_type="NEAR_DUPLICATE_POLICY_DEFERRED",
            raw_candidate_id=None,
            raw_blob_sha256=None,
            severity="INFO",
            blocks_strict_input=False,
            reason=(
                "ADR 0005 explicitly freezes Stage A at Exact-body CAS "
                "Deduplication and intentionally defers near-duplicate/copy/"
                "lineage inference."
            ),
            recommended_next_action=(
                "Introduce a separately approved versioned near-duplicate/"
                "copy/lineage policy only in the later stage where that "
                "inference is enabled."
            ),
        )
    )
    for error in recovery_scan_errors:
        missing_rows.append(
            make_row(
                "missing_coverage_ledger",
                issue_id=stable_id("issue", {"kind": "evidence_scan_error", "error": error}),
                issue_type="EVIDENCE_SCAN_ERROR",
                raw_candidate_id=None,
                raw_blob_sha256=None,
                severity="REVIEW",
                blocks_strict_input=False,
                reason=error,
                recommended_next_action="Inspect the listed evidence file; no recovery was inferred from an unreadable record.",
            )
        )

    raw_blob_count = len({row["raw_blob_sha256"] for row in raw_inventory_rows if row["raw_blob_sha256"]})
    coverage_rows = [
        make_row(
            "coverage_ledger",
            coverage_row_id=stable_id("coverage", {"stage": "4.3", "raw_blob_count": raw_blob_count}),
            upstream_scope="Stage 4.3 production discovery",
            upstream_observation_count=stage_4_3.get("counts", {}).get("production_observations"),
            upstream_unique_url_count=stage_4_3.get("counts", {}).get("unique_urls"),
            raw_blob_count=raw_blob_count,
            recovered_retrieval_count=len(recovery_rows),
            strict_retrieval_count=sum(bool(row["strict_source_input_eligible"]) for row in recovery_rows),
            comparison_status="NOT_COMPARABLE_WITHOUT_RAW_URL_MEMBERSHIP",
            reason="Discovery observations, URLs, retrieval events, and raw blobs are different units; Ticket A does not force their counts to match.",
        )
    ]

    table_rows = {
        "raw_inventory": sorted(raw_inventory_rows, key=lambda row: row["relative_path"]),
        "raw_hash_audit": sorted(hash_audit_rows, key=lambda row: row["relative_path"]),
        "retrievals": recovery_rows,
        "source_versions": sorted(source_version_rows, key=lambda row: row["source_version_id"]),
        "provenance_recovery_ledger": sorted(provenance_rows, key=lambda row: row["ledger_id"]),
        "body_variants": sorted(body_variant_rows_by_id.values(), key=lambda row: row["body_variant_id"]),
        "document_memberships": sorted(memberships, key=lambda row: row["membership_id"]),
        "document_clusters": cluster_rows,
        "lineage_edges": [],
        "near_duplicate_candidates": near_duplicate_rows,
        "missing_coverage_ledger": sorted(missing_rows, key=lambda row: row["issue_id"]),
        "coverage_ledger": coverage_rows,
    }
    table_manifests = {
        table_name: write_parquet_immutable(run_dir / "tables" / f"{table_name}.parquet", table_name, rows)
        for table_name, rows in table_rows.items()
    }

    source_lock = inspect_source_lock(repo_root)
    proposed_bundle = read_yaml(run_dir / "inputs" / "proposed_config_bundle.yaml")
    unreadable_raw_count = sum(row["read_status"] != "OK" for row in raw_inventory_rows)
    strict_raw_count = sum(bool(row["strict_input_eligible"]) for row in raw_inventory_rows)
    unresolved_raw_count = sum(row["source_provenance_status"] == "UNRESOLVED_NO_ACQUISITION_EVIDENCE" for row in raw_inventory_rows)
    blockers: list[dict[str, Any]] = []
    if stage_4_3.get("status") != "PASS":
        blockers.append({"id": "STAGE_4_3_RECONCILIATION", "detail": f"Stage 4.3 reconciliation status is {stage_4_3.get('status')}"})
    if source_lock["status"] != "PASS":
        blockers.append({"id": "SOURCE_LOCK", "detail": source_lock["reason"], "items": source_lock["items"]})
    if proposed_bundle.get("status") != "FROZEN":
        blockers.append({"id": "CONFIG_BASELINE", "detail": f"Config bundle is {proposed_bundle.get('status')}, not FROZEN"})
    if unreadable_raw_count:
        blockers.append({"id": "RAW_READ_ERRORS", "detail": f"{unreadable_raw_count} raw paths could not be read"})
    if unresolved_raw_count:
        blockers.append({"id": "UNRESOLVED_RAW_PROVENANCE", "detail": f"{unresolved_raw_count} raw paths lack direct acquisition evidence"})
    if any(row["blocks_strict_input"] and row["issue_type"] == "NEAR_DUPLICATE_POLICY_UNFROZEN" for row in missing_rows):
        blockers.append({"id": "NEAR_DUPLICATE_POLICY", "detail": "Near-duplicate/copy/lineage policy is not frozen"})
    input_lock_semantic = {
        "run_id": run_id,
        "status": "READY" if not blockers else "BLOCKED",
        "raw_scope": str(RAW_SCOPE_RELATIVE.as_posix()),
        "execution_code_fingerprint_sha256": package_fingerprint(repo_root),
        "source_lock": source_lock,
        "config_bundle_status": proposed_bundle.get("status"),
        "stage_4_3_reconciliation_status": stage_4_3.get("status"),
        "table_semantic_hashes": {name: manifest["semantic_sha256"] for name, manifest in table_manifests.items()},
        "raw_summary": {
            "raw_paths": len(raw_inventory_rows),
            "distinct_raw_hashes": raw_blob_count,
            "strict_raw_paths": strict_raw_count,
            "unresolved_raw_paths": unresolved_raw_count,
            "read_error_paths": unreadable_raw_count,
            "retrieval_records": len(recovery_rows),
            "body_variants": len(body_variant_rows_by_id),
            "exact_clusters": len(cluster_rows),
        },
        "blockers": blockers,
    }
    input_lock = {
        **input_lock_semantic,
        "created_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(input_lock_semantic),
    }
    write_json_immutable(run_dir / "inputs" / "input_lock.json", input_lock)

    readiness_semantic = {
        "ticket": "A",
        "implementation_status": "COMPLETE_WITH_READINESS_BLOCKERS",
        "scientific_input_readiness": input_lock_semantic["status"],
        "raw_summary": input_lock_semantic["raw_summary"],
        "blockers": blockers,
        "scope_exclusions": ["LLM inference", "pilot", "full corpus execution", "network refetch", "Neo4j materialization"],
    }
    readiness = {
        **readiness_semantic,
        "reported_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(readiness_semantic),
    }
    write_json_immutable(run_dir / "reports" / "input_readiness_report.json", readiness)
    append_jsonl(
        run_dir / "logs" / "inventory_operations.jsonl",
        {
            "event_type": "inventory_completed",
            "run_id": run_id,
            "occurred_at_real": utc_now_iso(),
            "input_lock_semantic_sha256": input_lock["semantic_sha256"],
            "raw_inventory_semantic_sha256": _artifact_semantic_hash(run_dir, "raw_inventory"),
        },
    )
    return {
        "run_id": run_id,
        "input_lock_status": input_lock["status"],
        "raw_summary": input_lock_semantic["raw_summary"],
        "stage_4_3_status": stage_4_3.get("status"),
        "table_write_statuses": {name: manifest["write_status"] for name, manifest in table_manifests.items()},
    }
