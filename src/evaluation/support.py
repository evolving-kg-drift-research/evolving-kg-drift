"""Protocol complete-support eligibility without fabricated zero drift."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def aggregate_complete_support(
    entities: Sequence[str], transition: str, rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    unique = sorted(set(entities))
    missing = []
    for e in unique:
        row = rows.get((transition, e))
        if (row is None or row.get("available") is not True
                or any(not isinstance(row.get(k), (int, float)) or not math.isfinite(row[k])
                       for k in ("SED_plus", "signed_excess"))):
            missing.append(e)
    if not unique or missing:
        return {"eligible": False, "SED_plus": None, "signed_excess": None,
                "unavailable_reason": "INCOMPLETE_SUPPORT", "missing_entities": missing}
    def median(key: str) -> float:
        values = sorted(rows[transition, e][key] for e in unique)
        n = len(values)
        return (values[(n - 1) // 2] + values[n // 2]) / 2

    return {"eligible": True,
            "SED_plus": median("SED_plus"),
            "signed_excess": median("signed_excess"),
            "unavailable_reason": "", "missing_entities": []}
