"""
Guided form schemas for Flutter / WhatsApp state machines (minimal typing).
"""
from __future__ import annotations

from apps.common.enums import UserRole


def guided_forms_for_role(*, role: str, lang: str) -> dict:
    lang = (lang or "en")[:8]
    farmer_steps = [
        {"id": "farm.name", "type": "text", "prompt_key": "guided.farm_name"},
        {"id": "farm.district", "type": "choice", "options_from": "districts"},
        {"id": "farm.size", "type": "number", "unit": "ha"},
    ]
    lot_steps = [
        {"id": "lot.code", "type": "text"},
        {"id": "lot.season", "type": "pick_season"},
    ]
    planting_steps = [
        {"id": "planting.when", "type": "quick_date", "options": ["today", "yesterday", "other"]},
        {"id": "planting.qty", "type": "number", "optional": True},
    ]
    buyer_grade = [
        {"id": "grade.lot", "type": "pick_lot"},
        {"id": "grade.code", "type": "choice", "options": ["C1L", "C2L", "C3L"]},
        {"id": "grade.note", "type": "text", "optional": True},
    ]
    buyer_sale = [
        {"id": "sale.lot", "type": "pick_lot"},
        {"id": "sale.price", "type": "money", "currency": "USD"},
    ]
    auditor_verify = [
        {"id": "verify.mode", "type": "choice", "options": ["upload", "hash", "recent"]},
    ]

    if role == UserRole.SMALLHOLDER_FARMER:
        return {
            "locale": lang,
            "flows": {
                "register_farm": {"steps": farmer_steps},
                "create_lot": {"steps": lot_steps},
                "add_planting": {"steps": planting_steps},
            },
        }
    if role == UserRole.BUYER_CONTRACTOR:
        return {
            "locale": lang,
            "flows": {
                "record_grading": {"steps": buyer_grade},
                "record_sale": {"steps": buyer_sale},
            },
        }
    if role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return {"locale": lang, "flows": {"verify_doc": {"steps": auditor_verify}}}
    return {"locale": lang, "flows": {}}
