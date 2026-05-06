"""
Ridge regression yield forecaster trained on the organisation's historical seasons.

Design notes (so accuracy claims are honest):

- **Features**: ``[1, expected_yield_kg_z, size_ha_z]`` — bias + two z-score-standardised
  numeric features. Standardisation makes the L2 penalty (``ridge_lambda``) invariant to
  feature scale; without it the size term would be effectively unpenalised.
- **Closed-form solve**: ``w = (XᵀX + λI)⁻¹ Xᵀ y`` over a 3×3 system; no sklearn dependency.
- **Predictions**: clipped to ``[0, max(2.5 × max(actual), 1500)]``. Yields cannot be
  negative and the ridge plane should not extrapolate to absurd magnitudes for tiny orgs.
- **Evaluation**: in-sample MAE / MAPE / RMSE / R² are always returned; a k-fold CV
  (k = min(5, n // 2)) is reported when ``n ≥ 5`` so consumers can see *out-of-sample*
  error rather than an over-optimistic training-set fit.

This module deliberately has no external ML dependency so it can run offline inside the
Django process and be cited in coursework as an applied statistical model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from apps.seasons.models import FarmSeasonAssociation


@dataclass(frozen=True)
class RidgeYieldFit:
    """Fitted ridge model over standardised features."""

    weights: tuple[float, float, float]  # bias, w_exp_z, w_size_z
    feature_means: tuple[float, float]   # mean(expected_yield_kg), mean(size_ha)
    feature_stds: tuple[float, float]    # std (with floor) for the two features
    n_samples: int
    ridge_lambda: float
    target_max_clip: float
    in_sample_metrics: dict = field(default_factory=dict)
    cv_metrics: dict = field(default_factory=dict)


def collect_org_yield_training_rows(organization) -> list[tuple[float, float, float]]:
    """Returns rows of (expected_yield_kg, size_ha, actual_yield_kg)."""
    rows: list[tuple[float, float, float]] = []
    qs = (
        FarmSeasonAssociation.objects.filter(farm__organization=organization)
        .select_related("farm", "season")
        .iterator(chunk_size=200)
    )
    for assoc in qs:
        act = assoc.season.actual_yield_kg
        if act is None:
            continue
        exp = float(assoc.season.expected_yield_kg or Decimal("400"))
        size = float(assoc.farm.size_hectares or Decimal("1"))
        if size <= 0:
            size = 1.0
        rows.append((exp, size, float(act)))
    return rows


def _standardise(values: list[float]) -> tuple[float, float, list[float]]:
    """Return (mean, std_with_floor, z-scored values). Std floor avoids divide-by-zero."""
    if not values:
        return 0.0, 1.0, []
    n = len(values)
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n
    sd = math.sqrt(var) if var > 0 else 0.0
    sd = max(sd, 1e-3)
    return mu, sd, [(v - mu) / sd for v in values]


def _mat3_inv(a: list[list[float]]) -> list[list[float]] | None:
    det = (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )
    if abs(det) < 1e-18:
        return None
    invdet = 1.0 / det
    return [
        [
            (a[1][1] * a[2][2] - a[1][2] * a[2][1]) * invdet,
            (a[0][2] * a[2][1] - a[0][1] * a[2][2]) * invdet,
            (a[0][1] * a[1][2] - a[0][2] * a[1][1]) * invdet,
        ],
        [
            (a[1][2] * a[2][0] - a[1][0] * a[2][2]) * invdet,
            (a[0][0] * a[2][2] - a[0][2] * a[2][0]) * invdet,
            (a[0][2] * a[1][0] - a[0][0] * a[1][2]) * invdet,
        ],
        [
            (a[1][0] * a[2][1] - a[1][1] * a[2][0]) * invdet,
            (a[0][1] * a[2][0] - a[0][0] * a[2][1]) * invdet,
            (a[0][0] * a[1][1] - a[0][1] * a[1][0]) * invdet,
        ],
    ]


def _solve_ridge(
    feature_rows: list[list[float]],
    targets: list[float],
    *,
    ridge_lambda: float,
) -> tuple[float, float, float] | None:
    a = [[0.0] * 3 for _ in range(3)]
    bvec = [0.0, 0.0, 0.0]
    for x, y in zip(feature_rows, targets, strict=True):
        for i in range(3):
            bvec[i] += x[i] * y
            for j in range(3):
                a[i][j] += x[i] * x[j]
    # Penalise non-bias terms only — standard ridge convention.
    a[1][1] += ridge_lambda
    a[2][2] += ridge_lambda
    inv = _mat3_inv(a)
    if inv is None:
        return None
    w = [sum(inv[i][j] * bvec[j] for j in range(3)) for i in range(3)]
    return (w[0], w[1], w[2])


def _predict(w: tuple[float, float, float], exp_z: float, size_z: float) -> float:
    return w[0] + w[1] * exp_z + w[2] * size_z


def _regression_metrics(actual: list[float], predicted: list[float]) -> dict:
    """MAE, MAPE (%), RMSE, R². Returns 0/None safely on degenerate input."""
    n = len(actual)
    if n == 0 or n != len(predicted):
        return {"n": n, "mae": None, "mape_percent": None, "rmse": None, "r2": None}
    abs_errs = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
    sq_errs = [(a - p) ** 2 for a, p in zip(actual, predicted, strict=True)]
    mae = sum(abs_errs) / n
    rmse = math.sqrt(sum(sq_errs) / n)
    pct_terms = [
        abs(a - p) / abs(a) for a, p in zip(actual, predicted, strict=True) if a != 0
    ]
    mape_percent = (sum(pct_terms) / len(pct_terms) * 100.0) if pct_terms else None
    mean_actual = sum(actual) / n
    ss_tot = sum((a - mean_actual) ** 2 for a in actual)
    ss_res = sum(sq_errs)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else None
    return {
        "n": n,
        "mae": round(mae, 3),
        "mape_percent": round(mape_percent, 2) if mape_percent is not None else None,
        "rmse": round(rmse, 3),
        "r2": round(r2, 4) if r2 is not None else None,
    }


def _kfold_indices(n: int, k: int, *, seed: int = 17) -> list[list[int]]:
    """Deterministic round-robin folds (stable across runs without random)."""
    folds: list[list[int]] = [[] for _ in range(k)]
    for i in range(n):
        # Mix index with seed so order isn't always identical, but is reproducible.
        folds[(i * seed + i) % k].append(i)
    return [f for f in folds if f]


def fit_ridge_yield(
    samples: list[tuple[float, float, float]],
    *,
    ridge_lambda: float = 2.0,
    min_samples: int = 5,
) -> RidgeYieldFit | None:
    """
    Fit ridge regression on (expected, size, actual) tuples.

    Returns ``None`` when ``len(samples) < min_samples`` (we deliberately do not
    publish a model fit on tiny datasets — the forecast service falls back to the
    deterministic baseline in that case).
    """
    if len(samples) < min_samples:
        return None

    expected = [s[0] for s in samples]
    size = [s[1] for s in samples]
    actual = [s[2] for s in samples]

    mu_exp, sd_exp, exp_z = _standardise(expected)
    mu_size, sd_size, size_z = _standardise(size)
    feature_rows = [[1.0, exp_z[i], size_z[i]] for i in range(len(samples))]

    weights = _solve_ridge(feature_rows, actual, ridge_lambda=ridge_lambda)
    if weights is None:
        return None

    in_sample_pred = [_predict(weights, feature_rows[i][1], feature_rows[i][2]) for i in range(len(samples))]
    in_sample = _regression_metrics(actual, in_sample_pred)

    cv = {"k": 0, "skipped_reason": "n<5"}
    if len(samples) >= 5:
        k = min(5, len(samples) // 2)
        if k >= 2:
            folds = _kfold_indices(len(samples), k)
            cv_actual: list[float] = []
            cv_pred: list[float] = []
            for hold_idx, fold_indices in enumerate(folds):
                train_rows: list[list[float]] = []
                train_targets: list[float] = []
                for i in range(len(samples)):
                    if i in fold_indices:
                        continue
                    train_rows.append(feature_rows[i])
                    train_targets.append(actual[i])
                if len(train_rows) < 3:
                    continue
                fold_w = _solve_ridge(train_rows, train_targets, ridge_lambda=ridge_lambda)
                if fold_w is None:
                    continue
                for i in fold_indices:
                    cv_actual.append(actual[i])
                    cv_pred.append(_predict(fold_w, feature_rows[i][1], feature_rows[i][2]))
            cv = _regression_metrics(cv_actual, cv_pred)
            cv["k"] = k
            cv["scheme"] = "round_robin_kfold"

    target_max_clip = max(max(actual) * 2.5, 1500.0)

    return RidgeYieldFit(
        weights=weights,
        feature_means=(mu_exp, mu_size),
        feature_stds=(sd_exp, sd_size),
        n_samples=len(samples),
        ridge_lambda=ridge_lambda,
        target_max_clip=target_max_clip,
        in_sample_metrics=in_sample,
        cv_metrics=cv,
    )


def predict_yield_kg(fit: RidgeYieldFit, expected_yield_kg: float, size_ha: float) -> float:
    """Apply the fit; clipped to ``[0, target_max_clip]`` to avoid extrapolation hallucinations."""
    mu_exp, mu_size = fit.feature_means
    sd_exp, sd_size = fit.feature_stds
    exp_z = (float(expected_yield_kg) - mu_exp) / sd_exp
    size_z = (float(size_ha) - mu_size) / sd_size
    raw = _predict(fit.weights, exp_z, size_z)
    return max(0.0, min(raw, fit.target_max_clip))


def predict_yield_band_kg(
    fit: RidgeYieldFit,
    expected_yield_kg: float,
    size_ha: float,
) -> tuple[float, float, float]:
    """
    Returns (low, mid, high). The half-width uses CV RMSE when available
    (1.0σ ≈ 68%), or a 12 % fallback. Always non-negative.
    """
    mid = predict_yield_kg(fit, expected_yield_kg, size_ha)
    rmse = fit.cv_metrics.get("rmse") if fit.cv_metrics else None
    if rmse is None:
        rmse = fit.in_sample_metrics.get("rmse")
    if rmse is None or rmse <= 0:
        half = max(40.0, abs(mid) * 0.12)
    else:
        half = max(40.0, float(rmse))
    low = max(0.0, mid - half)
    high = min(fit.target_max_clip, mid + half)
    return (low, mid, high)
