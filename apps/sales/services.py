from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from apps.common.enums import LotStatus
from apps.grading.models import GradeRecord
from apps.lots.models import Lot
from apps.sales.models import GradeAnnualPrice, Sale, SaleStatus


def _fallback_price_for_grade(grade: str) -> Decimal:
    # Deterministic fallback when annual schedule is not configured for a grade/year.
    digits = "".join(ch for ch in (grade or "") if ch.isdigit())
    if not digits:
        return Decimal("0.50")
    return Decimal("0.50") * Decimal(digits)


def _price_for_grade_year(*, grade: str, year: int) -> Decimal:
    row = (
        GradeAnnualPrice.objects.filter(grade=grade, year=year)
        .order_by("-updated_at")
        .first()
    )
    if row is not None:
        return row.price_per_kg
    return _fallback_price_for_grade(grade)


def build_grading_trail(*, lot: Lot, year: int) -> list[dict]:
    records = list(GradeRecord.objects.filter(lot=lot).order_by("graded_at", "created_at"))
    trail: list[dict] = []
    for idx, rec in enumerate(records, start=1):
        ppk = _price_for_grade_year(grade=rec.grade, year=year)
        weight = Decimal(rec.weight_kg or 0)
        subtotal = (weight * ppk).quantize(Decimal("0.01"))
        trail.append(
            {
                "bale_index": idx,
                "grade": rec.grade,
                "weight_kg": float(weight),
                "price_per_kg": float(ppk),
                "subtotal": float(subtotal),
                "graded_at": rec.graded_at.isoformat() if rec.graded_at else None,
                "quality_score": rec.quality_score,
                "moisture_percent": float(rec.moisture_percent) if rec.moisture_percent is not None else None,
            }
        )
    return trail


def generate_ai_pricing_note(*, trail: list[dict], year: int) -> str:
    if not trail:
        return "AI note: No grading trail is available to explain sale pricing."
    total_weight = sum(float(row.get("weight_kg") or 0) for row in trail)
    total_amount = sum(float(row.get("subtotal") or 0) for row in trail)
    avg_price = 0.0 if total_weight <= 0 else total_amount / total_weight
    top = sorted(trail, key=lambda r: float(r.get("subtotal") or 0), reverse=True)[:2]
    top_bits = ", ".join(
        f"bale {t['bale_index']} ({t['grade']}, {t['weight_kg']}kg @ {t['price_per_kg']}/kg)"
        for t in top
    )
    return (
        f"AI pricing note ({year} schedule): total is driven by per-bale grade pricing and weight. "
        f"Weighted average price is {avg_price:.2f}/kg across {len(trail)} bale(s). "
        f"Highest contributors: {top_bits}."
    )


def create_or_refresh_sale_from_grading(*, lot: Lot, buyer, year: int | None = None) -> Sale:
    year = year or timezone.now().year
    trail = build_grading_trail(lot=lot, year=year)
    total_weight = sum(Decimal(str(row.get("weight_kg") or 0)) for row in trail)
    total_amount = sum(Decimal(str(row.get("subtotal") or 0)) for row in trail)
    if total_weight > 0:
        ppk = (total_amount / total_weight).quantize(Decimal("0.01"))
    else:
        ppk = Decimal("0.00")
    note = generate_ai_pricing_note(trail=trail, year=year)

    sale = (
        Sale.objects.filter(lot=lot, buyer=buyer, status__in=[SaleStatus.PENDING, SaleStatus.ACCEPTED])
        .order_by("-created_at")
        .first()
    )
    if sale is None:
        sale = Sale(
            lot=lot,
            buyer=buyer,
            sale_date=timezone.now(),
        )
    sale.price_per_kg = ppk
    sale.total_weight_kg = total_weight.quantize(Decimal("0.01"))
    sale.total_amount = total_amount.quantize(Decimal("0.01"))
    sale.currency = "USD"
    sale.status = SaleStatus.PENDING
    sale.annual_price_year = year
    sale.grading_trail = trail
    sale.ai_pricing_note = note
    sale.notes = (sale.notes or "").strip()
    sale.save()

    if lot.status == LotStatus.GRADED:
        lot.status = LotStatus.LISTED_FOR_SALE
        lot.save(update_fields=["status", "updated_at"])
    return sale
