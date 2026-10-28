"""Unit tests for Vietnamese QA Question Formulations (1-hop and 2-hop latent bridge)."""
from __future__ import annotations

from evaluation.qa_questions import (
    RELATION_TEMPLATES_1HOP,
    RELATION_TEMPLATES_2HOP,
    format_1hop_question,
    format_2hop_question,
    format_qa_question,
    infer_entity_kind,
)


def test_relation_templates_completeness():
    """Verify all 10 canonical relations exist in 1-hop templates."""
    expected_relations = {
        "works_at",
        "is_CEO_of",
        "released_by",
        "partners_with",
        "invested_in",
        "version_of",
        "integrated_into",
        "based_on",
        "succeeded_by",
        "acquired_by",
    }
    assert set(RELATION_TEMPLATES_1HOP.keys()) == expected_relations


def test_2hop_latent_bridge_templates_completeness():
    """Verify all 11 recurring 2-hop relation pairs exist in 2-hop templates."""
    expected_pairs = {
        ("works_at", "partners_with"),
        ("released_by", "partners_with"),
        ("works_at", "invested_in"),
        ("integrated_into", "released_by"),
        ("is_CEO_of", "partners_with"),
        ("version_of", "succeeded_by"),
        ("partners_with", "partners_with"),
        ("based_on", "released_by"),
        ("acquired_by", "works_at"),
        ("invested_in", "partners_with"),
        ("succeeded_by", "version_of"),
    }
    assert set(RELATION_TEMPLATES_2HOP.keys()) == expected_pairs


def test_entity_kind_inference():
    assert infer_entity_kind("TS Lê Bá Chung") == "SCIENTIST"
    assert infer_entity_kind("Tiến sĩ Phan Hoàng Vũ") == "SCIENTIST"
    assert infer_entity_kind("GPT-4o") == "AI_MODEL"
    assert infer_entity_kind("DeepSeek-Reasoner") == "AI_MODEL"
    assert infer_entity_kind("iPhone 16e") == "DEVICE"
    assert infer_entity_kind("màn hình ôtô thông minh Android AI ADAS Utour") == "DEVICE"
    assert infer_entity_kind("macOS 15.4") == "OS"
    assert infer_entity_kind("Super Vietnam 2025 PitchFest") == "EVENT"


def test_1hop_formatting():
    q_work = format_1hop_question("TS Lê Bá Chung", "works_at")
    assert 'Chuyên gia/nhà nghiên cứu "TS Lê Bá Chung"' in q_work
    assert "cơ quan/tổ chức nào?" in q_work

    q_ceo = format_1hop_question("Sam Altman", "is_CEO_of")
    assert 'Giám đốc điều hành (CEO)' in q_ceo
    assert '"Sam Altman"' in q_ceo

    q_rel = format_1hop_question("DeepSeek-Chat", "released_by")
    assert 'Mô hình/hệ thống AI "DeepSeek-Chat"' in q_rel

    q_ver = format_1hop_question("iOS 18.4", "version_of")
    assert 'Hệ điều hành/phiên bản "iOS 18.4"' in q_ver

    q_acq = format_1hop_question("Twitter", "acquired_by")
    assert 'sáp nhập hoặc mua lại' in q_acq


def test_2hop_latent_bridge_formatting():
    # Intermediate entity must NEVER appear in question
    q_2hop = format_2hop_question("Brad Smith", ["works_at", "partners_with"])
    assert "Microsoft" not in q_2hop
    assert '"Brad Smith"' in q_2hop
    assert "hợp tác chiến lược" in q_2hop

    q_2hop_ceo = format_2hop_question("Young Liu", ["is_CEO_of", "partners_with"])
    assert "Foxconn" not in q_2hop_ceo
    assert '"Young Liu"' in q_2hop_ceo
    assert "CEO" in q_2hop_ceo

    q_2hop_tech = format_2hop_question("Nomi", ["integrated_into", "released_by"])
    assert "GPT-4o" not in q_2hop_tech
    assert '"Nomi"' in q_2hop_tech
    assert "nghiên cứu và phát hành" in q_2hop_tech


def test_format_qa_question_dispatch():
    q1 = format_qa_question("Apple Intelligence", ["released_by"])
    assert '"Apple Intelligence"' in q1
    assert "phát hành" in q1

    q2 = format_qa_question("iPhone SE 3", ["succeeded_by", "version_of"])
    assert '"iPhone SE 3"' in q2
    assert "kế nhiệm" in q2
    assert "iPhone 16e" not in q2
