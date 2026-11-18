from __future__ import annotations

import pytest

from kg_pipeline.entity_map_v2 import canonical_key, entity_id_v2, is_generic_mention


@pytest.mark.parametrize("a,b", [
    ("FPT", "tập đoàn FPT"), ("Tập đoàn FPT", "FPT"), ("Grok 3", "Grok-3"),
    ("Amazon Web Services (AWS)", "Amazon Web Services"), ("Đại học Stanford (Mỹ)", "Đại học Stanford"),
    ("ông Trương Gia Bình", "Trương Gia Bình"), ("Ông Kenneth Tse", "kenneth tse"),
    ("Sumitomo Corporation", "Sumitomo"), ("HP Inc.", "HP"), ('robot K2 "Bumblebee"', "robot K2 Bumblebee"),
])
def test_equivalent_mentions_share_a_key(a: str, b: str) -> None:
    assert canonical_key(a) == canonical_key(b)


@pytest.mark.parametrize("a,b", [
    ("Bộ Công an (A05)", "Bộ Công an"),            # digit parenthetical = a sub-unit code, kept apart
    ("Zenbook 14 (UM3406GA)", "Zenbook 14"),
    ("Bà Rịa - Vũng Tàu", "Rịa Vũng Tàu"),         # place name, not the title "bà"
    ("Ngân hàng Nhà nước", "Nhà nước"),            # official name keeps its class word
    ("Meta Platforms", "Meta"),                     # corporate-suffix links are proposals, not applied
    ("công ty robot Kepler", "Kepler"),             # lowercase noun after the class word: not stripped
])
def test_distinct_entities_are_not_merged(a: str, b: str) -> None:
    assert canonical_key(a) != canonical_key(b)


def test_key_never_empty_and_stable() -> None:
    assert canonical_key("công ty") == "công ty"
    assert canonical_key("(AWS)") == "(aws)"
    assert canonical_key("Apple") == canonical_key(" Apple ")


@pytest.mark.parametrize("name", ["ông", "Ông", "công ty", "Hãng", "Mô hình", "người này", "laptop mới",
                                  "kho dữ liệu dùng chung", "hai công ty công nghệ quốc phòng"])
def test_generic_mentions(name: str) -> None:
    assert is_generic_mention(name)


@pytest.mark.parametrize("name", ["xAI", "iPhone 16", "iOS", "o1", "macOS", "Apple", "Google", "Ông Trương Gia Bình",
                                  "tập đoàn FPT", "titanwings", "ChatGPT"])
def test_named_entities_are_not_generic(name: str) -> None:
    assert not is_generic_mention(name)


def test_entity_id_is_a_pure_function_of_the_key() -> None:
    assert entity_id_v2("fpt") == entity_id_v2("fpt") and entity_id_v2("fpt") != entity_id_v2("apple")
    assert entity_id_v2("fpt").startswith("ent2_")
