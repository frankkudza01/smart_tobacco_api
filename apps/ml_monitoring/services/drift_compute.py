"""
Simplified drift signals: PSI-like bin comparison + residual shift flags (MVP).
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Sequence


def _psi(expected: Sequence[float], actual: Sequence[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    e_min, e_max = min(expected), max(expected)
    if e_max == e_min:
        return 0.0
    width = (e_max - e_min) / bins

    def hist(vals):
        h = [1e-6] * bins
        for v in vals:
            i = min(bins - 1, int((v - e_min) / width)) if width else 0
            h[i] += 1
        s = sum(h)
        return [x / s for x in h]

    E = hist(expected)
    A = hist(actual)
    psi = 0.0
    for i in range(bins):
        psi += (A[i] - E[i]) * math.log((A[i] + 1e-9) / (E[i] + 1e-9))
    return float(psi)


def compute_drift_for_org(*, organization, baseline_values: list[float], recent_values: list[float]) -> dict:
    psi = _psi(baseline_values, recent_values)
    triggered = psi > 0.25
    return {
        "psi": round(psi, 4),
        "triggered": triggered,
        "reason": "feature_distribution_shift" if triggered else "",
    }


def should_trigger_retrain(*, mape_yield: Decimal | None, days_high: int = 3) -> bool:
    if mape_yield is None:
        return False
    return float(mape_yield) > 0.15
