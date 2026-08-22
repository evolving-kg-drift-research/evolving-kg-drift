from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative: str):
    with (ROOT / relative).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_core_engineering_docs_exist():
    required = [
        "docs/architecture.md",
        "docs/modules.md",
        "docs/data_and_artifacts.md",
        "docs/gates_and_freeze.md",
        "docs/team_handoff.md",
        "CONTRIBUTING.md",
        ".github/pull_request_template.md",
    ]
    for relative in required:
        assert (ROOT / relative).is_file(), relative


def test_experiment_manifest_template_matches_schema_required_fields():
    schema = load_yaml("configs/schemas/experiment_manifest.schema.yaml")
    template = load_yaml("experiments/MANIFEST_TEMPLATE.yaml")

    for key in schema["required"]:
        assert key in template, key

    for key in schema["fields"]["git"]["required"]:
        assert key in template["git"], f"git.{key}"

    for key in schema["fields"]["inputs"]["required"]:
        assert key in template["inputs"], f"inputs.{key}"

    for key in schema["fields"]["access"]["required"]:
        assert key in template["access"], f"access.{key}"


def test_w7_freeze_template_contains_registered_freeze_components():
    template = load_yaml("data/manifests/W7_FREEZE_TEMPLATE.yaml")
    required = {
        "protocol_version",
        "protocol_sha256",
        "git_commit",
        "data_hash",
        "snapshot_manifest_hash",
        "query_hash",
        "candidate_universe_hashes",
        "pseudo_hash",
        "wcb",
        "locked_access_state",
        "dry_run",
    }
    assert required.issubset(template)
    assert {"seed", "draws"}.issubset(template["wcb"])


def test_temporal_fixture_set_exists():
    fixtures = ROOT / "tests" / "fixtures" / "temporal"
    expected = {
        "normal_publication.json",
        "late_correction.json",
        "historical_ingestion.json",
    }
    assert expected.issubset({p.name for p in fixtures.glob("*.json")})
