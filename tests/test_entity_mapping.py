from kg_pipeline.adjudication import fuzzy_match_entity


def test_fuzzy_match_exact():
    catalog = {"Apple Inc": "ent_apple", "Microsoft": "ent_msft"}
    assert fuzzy_match_entity("Apple Inc", catalog) == "ent_apple"


def test_fuzzy_match_case_insensitive():
    catalog = {"Apple Inc": "ent_apple"}
    assert fuzzy_match_entity("apple inc", catalog) == "ent_apple"
    assert fuzzy_match_entity("APPLE INC", catalog) == "ent_apple"


def test_fuzzy_match_substring():
    catalog = {"Apple Inc": "ent_apple"}
    assert fuzzy_match_entity("Apple", catalog) == "ent_apple"


def test_fuzzy_match_not_found():
    catalog = {"Apple Inc": "ent_apple"}
    assert fuzzy_match_entity("Google", catalog) is None
