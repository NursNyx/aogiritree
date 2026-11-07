from __future__ import annotations

from typing import Dict, Optional

from .checklist import CriterionConfig, CriterionType


def calculate_weighted_score(
    criteria: list[CriterionConfig],
    criterion_values: Dict[str, bool | int | None],
) -> Optional[float]:
    """Return normalized 0-100 score with N/A redistribution.

    N/A redistribution is implemented by normalizing earned points by only the
    applicable weighted criteria. Returns None when nothing weighted applies.
    """
    earned_points = 0.0
    applicable_weight = 0.0

    for criterion in criteria:
        if criterion.weight <= 0:
            continue

        value = criterion_values.get(criterion.criterion_id)
        if value is None and criterion.na_allowed:
            continue

        applicable_weight += criterion.weight

        if criterion.type == CriterionType.BOOLEAN:
            if value is True:
                earned_points += criterion.weight
        else:
            if value is None:
                continue
            if criterion.scale is None:
                raise ValueError(f"Scale is required for {criterion.criterion_id}")
            if value not in criterion.scale:
                raise ValueError(
                    f"Invalid value {value!r} for criterion {criterion.criterion_id}"
                )
            max_value = max(criterion.scale)
            if max_value == 0:
                continue
            earned_points += (float(value) / float(max_value)) * criterion.weight

    if applicable_weight == 0:
        return None

    return round((earned_points / applicable_weight) * 100.0, 2)


def extract_critical_flag(criterion_values: Dict[str, bool | int | None]) -> bool:
    value = criterion_values.get("critical")
    return bool(value is True)
