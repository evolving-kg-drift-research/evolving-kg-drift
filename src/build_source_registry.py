from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]

SOURCES_FILE = ROOT / "config" / "sources.yaml"
OUTPUT_FILE = ROOT / "data" / "manifests" / "source_registry.parquet"


REQUIRED_FIELDS = [
    "source_id",
    "name",
    "domain",
    "source_type",
    "rss",
    "enabled",
    "trust_notes",
    "archive_availability",
    "robots_legal_notes",
]


def main():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    registry_version = config.get("source_registry_version")

    if not registry_version:
        raise ValueError("Thiếu source_registry_version trong sources.yaml")

    sources = config.get("sources", {})

    if not sources:
        raise ValueError("sources.yaml chưa có nguồn nào")

    rows = []

    for source_key, source in sources.items():
        missing = [
            field
            for field in REQUIRED_FIELDS
            if field not in source
        ]

        if missing:
            raise ValueError(
                f"Nguồn '{source_key}' thiếu field: {missing}"
            )

        row = {
            "source_registry_version": registry_version,
            **{field: source[field] for field in REQUIRED_FIELDS},
        }

        rows.append(row)

    df = pd.DataFrame(rows)

    # Kiểm tra source_id không được trùng
    duplicated = df[df["source_id"].duplicated(keep=False)]

    if not duplicated.empty:
        raise ValueError(
            "Phát hiện source_id bị trùng:\n"
            + duplicated["source_id"].to_string(index=False)
        )

    # Sắp xếp để output deterministic
    df = df.sort_values("source_id").reset_index(drop=True)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(
        OUTPUT_FILE,
        index=False,
        engine="pyarrow",
    )

    print(f"[OK] Created: {OUTPUT_FILE}")
    print(f"[OK] Registry version: {registry_version}")
    print(f"[OK] Number of sources: {len(df)}")

    print("\nSource registry:")
    print(
        df[
            [
                "source_id",
                "domain",
                "source_type",
                "enabled",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()