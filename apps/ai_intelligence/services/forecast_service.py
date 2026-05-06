from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ai_intelligence.models import EvaluationMetricRun, ForecastPoint, ForecastRun
from apps.common.access import can_view_farm, can_view_lot, farms_queryset_for_user, lots_queryset_for_user
from apps.common.enums import ForecastModelType, ForecastRunStatus, ForecastSubjectType
from apps.common.org_utils import get_user_primary_organization
from apps.farms.models import Farm
from apps.lots.models import Lot

YIELD_HALLUCINATION_GUARDS = [
    "ridge_regression_closed_form",
    "feature_z_score_standardised",
    "predictions_clipped_non_negative",
    "predictions_clipped_to_2_5x_max_actual",
    "interval_half_width_from_cv_rmse",
    "kfold_cross_validation_when_n_ge_5",
]
PRICE_HALLUCINATION_GUARDS = [
    "deterministic_grade_basket_band",
    "no_external_llm_call",
]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_VERSION = "mvp-v1"


class ForecastService:
    @staticmethod
    def _accessible_filter(user, qs):
        if user.role == "SMALLHOLDER_FARMER":
            farm_ids = list(farms_queryset_for_user(user).values_list("id", flat=True))
            lot_ids = list(lots_queryset_for_user(user).values_list("id", flat=True))
            return qs.filter(
                Q(subject_type=ForecastSubjectType.FARM, subject_id__in=farm_ids)
                | Q(subject_type=ForecastSubjectType.LOT, subject_id__in=lot_ids)
                | Q(season__farm_associations__farm_id__in=farm_ids)
            ).distinct()
        if user.role == "BUYER_CONTRACTOR":
            lot_ids = list(lots_queryset_for_user(user).values_list("id", flat=True))
            return qs.filter(
                Q(subject_type=ForecastSubjectType.LOT, subject_id__in=lot_ids)
                | Q(season__lots__id__in=lot_ids)
            ).distinct()
        if user.role in ("REGULATOR_AUDITOR", "SYSTEM_ADMIN"):
            return qs
        return qs.none()

    @staticmethod
    def list_yield_forecasts(
        user,
        *,
        season_id: UUID | None = None,
        farm_id: UUID | None = None,
        lot_id: UUID | None = None,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        org = get_user_primary_organization(user)
        if org is None:
            return []
        qs = ForecastPoint.objects.filter(organization=org).filter(
            Q(model_version__icontains=ForecastModelType.YIELD)
        )
        if season_id:
            qs = qs.filter(season_id=season_id)
        if farm_id:
            try:
                farm = Farm.objects.get(id=farm_id)
            except Farm.DoesNotExist:
                return []
            if not can_view_farm(user, farm):
                return []
            qs = qs.filter(
                Q(subject_id=farm_id, subject_type=ForecastSubjectType.FARM)
                | Q(season__farm_associations__farm_id=farm_id)
            ).distinct()
        if lot_id:
            try:
                lot = Lot.objects.select_related("season", "farm").get(id=lot_id)
            except Lot.DoesNotExist:
                return []
            if not can_view_lot(user, lot):
                return []
            qs = qs.filter(
                Q(subject_id=lot_id, subject_type=ForecastSubjectType.LOT)
                | Q(season_id=lot.season_id)
            )

        qs = ForecastService._accessible_filter(user, qs)
        rows = qs.order_by("-point_timestamp")[:200]
        return [ForecastService._serialize_point(p) for p in rows]

    @staticmethod
    def list_price_forecasts(
        user,
        *,
        season_id: UUID | None = None,
        grade: str | None = None,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        org = get_user_primary_organization(user)
        if org is None:
            return []
        qs = ForecastPoint.objects.filter(organization=org).filter(
            Q(model_version__icontains=ForecastModelType.PRICE)
        )
        if season_id:
            qs = qs.filter(season_id=season_id)
        qs = ForecastService._accessible_filter(user, qs)
        if grade:
            qs = qs.filter(explain_summary__icontains=grade)
        rows = qs.order_by("-point_timestamp")[:200]
        return [ForecastService._serialize_point(p) for p in rows]

    @staticmethod
    def _serialize_point(p: ForecastPoint) -> dict[str, Any]:
        run = (
            ForecastRun.objects.filter(
                organization_id=p.organization_id,
                model_version=p.model_version,
            )
            .order_by("-trained_at")
            .first()
        )
        evaluation: dict[str, Any] = {}
        guards: list[str] = []
        if run:
            evaluation = {
                "model_version": run.model_version,
                "trained_at": run.trained_at.isoformat() if run.trained_at else None,
                "metrics": run.metrics_json or {},
            }
            guards = (run.metrics_json or {}).get("hallucination_guards") or []
        return {
            "id": str(p.id),
            "subject_type": p.subject_type,
            "subject_id": str(p.subject_id) if p.subject_id else None,
            "region_code": p.region_code or None,
            "season_id": str(p.season_id) if p.season_id else None,
            "point_timestamp": p.point_timestamp.isoformat(),
            "yhat": str(p.yhat),
            "yhat_lower": str(p.yhat_lower),
            "yhat_upper": str(p.yhat_upper),
            "model_version": p.model_version,
            "explain_summary": p.explain_summary[:2000] if p.explain_summary else "",
            "evaluation": evaluation,
            "hallucination_guards": guards,
        }

    @staticmethod
    @transaction.atomic
    def run_retrain_mvp(*, organization, model_type: str, created_by) -> ForecastRun:
        """Train (or set up) a yield/price forecast for the org and persist evaluation metrics.

        For ``model_type == YIELD`` and **n ≥ 5** historical actuals, fits the local
        ridge model from ``apps.ai_intelligence.local_models.ridge_yield`` and writes:

        - ``ForecastRun.metrics_json``: in-sample + k-fold CV (MAE/MAPE/RMSE/R²),
          model name, weights, λ, hallucination guards.
        - One row per CV metric in ``EvaluationMetricRun`` so the
          ``/api/v1/ai/metrics/evaluation/`` endpoint surfaces it.
        - Forecast intervals derived from CV RMSE (1σ band, never negative).

        For ``model_type == PRICE`` it writes the deterministic placeholder band; the
        response is tagged with ``deterministic_grade_basket_band`` in the guards list.
        """
        ridge_fit = None
        samples: list[tuple[float, float, float]] = []
        predict_band_fn = None
        if model_type == ForecastModelType.YIELD:
            from apps.ai_intelligence.local_models.ridge_yield import (
                collect_org_yield_training_rows,
                fit_ridge_yield,
                predict_yield_band_kg,
            )

            samples = collect_org_yield_training_rows(organization)
            ridge_fit = fit_ridge_yield(samples)
            if ridge_fit is not None:
                predict_band_fn = predict_yield_band_kg

        if model_type == ForecastModelType.YIELD and ridge_fit is not None:
            cv = ridge_fit.cv_metrics or {}
            cv_mape = cv.get("mape_percent")
            mape_tag = f"-cvmape{round(cv_mape)}" if isinstance(cv_mape, (int, float)) else ""
            model_version = f"local-ridge-{ridge_fit.n_samples}{mape_tag}-yield-v1"
            summary_why = (
                f"On-server ridge regression on {ridge_fit.n_samples} farm–season rows. "
                f"Features (z-scored): bias, expected_yield_kg, farm size ha; λ={ridge_fit.ridge_lambda}. "
                f"In-sample MAPE: {ridge_fit.in_sample_metrics.get('mape_percent')}; "
                f"CV ({cv.get('k')}-fold) MAPE: {cv_mape}."
            )
            metrics_json = {
                "model": "ridge_closed_form",
                "n_samples": ridge_fit.n_samples,
                "ridge_lambda": ridge_fit.ridge_lambda,
                "weights_bias_w_exp_w_size_z": list(ridge_fit.weights),
                "feature_means_exp_size": list(ridge_fit.feature_means),
                "feature_stds_exp_size": list(ridge_fit.feature_stds),
                "target_max_clip_kg": ridge_fit.target_max_clip,
                "in_sample": ridge_fit.in_sample_metrics,
                "cv": ridge_fit.cv_metrics,
                "hallucination_guards": list(YIELD_HALLUCINATION_GUARDS),
            }
        elif model_type == ForecastModelType.YIELD:
            n_obs = len(samples)
            model_version = f"{DEFAULT_MODEL_VERSION}-{model_type}"
            summary_why = (
                f"Insufficient historical actuals (n={n_obs} < 5); using deterministic baseline "
                "anchored on expected_yield_kg. No local ridge fit was published."
            )
            metrics_json = {
                "model": "baseline_expected_yield",
                "n_samples": n_obs,
                "in_sample": {"mape_percent": None, "note": "no fit; baseline only"},
                "cv": {"skipped_reason": "n<5"},
                "hallucination_guards": [
                    "no_external_llm_call",
                    "deterministic_baseline_when_n_lt_5",
                    "predictions_clipped_non_negative",
                ],
            }
        else:
            model_version = f"{DEFAULT_MODEL_VERSION}-{model_type}"
            summary_why = (
                "Deterministic grade-basket price band (MVP placeholder; not a learned model)."
            )
            metrics_json = {
                "model": "deterministic_basket_band",
                "in_sample": {"note": "no model trained"},
                "cv": {"skipped_reason": "deterministic"},
                "hallucination_guards": list(PRICE_HALLUCINATION_GUARDS),
            }

        run = ForecastRun.objects.create(
            organization=organization,
            model_type=model_type,
            model_version=model_version,
            trained_at=timezone.now(),
            status=ForecastRunStatus.RUNNING,
            metrics_json=metrics_json,
            summary_why=summary_why,
            created_by=created_by,
        )
        ForecastPoint.objects.filter(organization=organization, model_version=run.model_version).delete()
        farms = Farm.objects.filter(organization=organization, is_active=True)
        now = timezone.now()
        points: list[ForecastPoint] = []
        for farm in farms:
            for season in farm.seasons.all():
                base = season.expected_yield_kg or Decimal("400")
                if model_type == ForecastModelType.PRICE:
                    mid = Decimal("4.25")
                    low, high = Decimal("3.80"), Decimal("4.70")
                    explain = f"Grade basket price band for crop year {season.crop_year} (MVP)."
                elif ridge_fit is not None and predict_band_fn is not None:
                    exp = float(season.expected_yield_kg or 400)
                    size = float(farm.size_hectares or 1)
                    low_v, mid_v, high_v = predict_band_fn(ridge_fit, exp, max(size, 0.001))
                    mid = Decimal(str(round(mid_v, 2)))
                    low = Decimal(str(round(low_v, 2)))
                    high = Decimal(str(round(high_v, 2)))
                    explain = (
                        f"Season {season.crop_year}: ridge yield prediction from "
                        f"{ridge_fit.n_samples} historical org rows."
                    )
                else:
                    mid = base
                    low = base * Decimal("0.85")
                    high = base * Decimal("1.15")
                    explain = (
                        f"Season {season.crop_year}: deterministic baseline (no local fit)."
                    )
                points.append(
                    ForecastPoint(
                        organization=organization,
                        subject_type=ForecastSubjectType.FARM,
                        subject_id=farm.id,
                        season=season,
                        point_timestamp=now,
                        yhat=mid,
                        yhat_lower=low,
                        yhat_upper=high,
                        model_version=run.model_version,
                        explain_summary=explain,
                    )
                )
        ForecastPoint.objects.bulk_create(points)

        # Persist headline metrics so /ai/metrics/evaluation/ shows them.
        if ridge_fit is not None:
            for name, value in (
                ("MAE_in_sample", ridge_fit.in_sample_metrics.get("mae")),
                ("MAPE_in_sample_percent", ridge_fit.in_sample_metrics.get("mape_percent")),
                ("RMSE_in_sample", ridge_fit.in_sample_metrics.get("rmse")),
                ("R2_in_sample", ridge_fit.in_sample_metrics.get("r2")),
                ("MAPE_cv_percent", ridge_fit.cv_metrics.get("mape_percent")),
                ("RMSE_cv", ridge_fit.cv_metrics.get("rmse")),
            ):
                if value is None:
                    continue
                EvaluationMetricRun.objects.create(
                    organization=organization,
                    metric_name=name,
                    model_key="ridge_yield",
                    model_version=run.model_version,
                    value=Decimal(str(value)),
                    metrics_json={"source": "run_retrain_mvp"},
                    evaluated_at=now,
                    notes=f"Ridge yield model retrain id={run.id}",
                )

        run.status = ForecastRunStatus.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        return run
