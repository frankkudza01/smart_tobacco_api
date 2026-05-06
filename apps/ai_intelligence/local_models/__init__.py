"""On-server statistical / CV-lite models (no external LLM inference)."""

from apps.ai_intelligence.local_models.ridge_yield import (
    RidgeYieldFit,
    collect_org_yield_training_rows,
    fit_ridge_yield,
)

__all__ = [
    "RidgeYieldFit",
    "collect_org_yield_training_rows",
    "fit_ridge_yield",
]
