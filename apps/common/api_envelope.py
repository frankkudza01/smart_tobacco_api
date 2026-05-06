"""
Standard API success/error envelope helpers (optional use per view).

Success: { "success": true, "data": ..., "meta": {...}, "errors": [] }
Error:   { "success": false, "data": null, "meta": {...}, "errors": [...] }
"""

from __future__ import annotations

from typing import Any


def success_envelope(
    data: Any,
    *,
    meta: dict | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": meta or {},
        "errors": [],
    }


def error_envelope(
    errors: list[dict[str, Any]],
    *,
    meta: dict | None = None,
    status_code: int | None = None,
) -> dict[str, Any]:
    m = dict(meta or {})
    if status_code is not None:
        m["status_code"] = status_code
    return {
        "success": False,
        "data": None,
        "meta": m,
        "errors": errors,
    }


def drf_errors_to_list(data: dict) -> list[dict[str, Any]]:
    """Flatten DRF validation / error dict into {code, message, field} entries."""
    out: list[dict[str, Any]] = []
    for key, val in data.items():
        if key in ("detail", "non_field_errors"):
            if isinstance(val, list):
                for item in val:
                    out.append(
                        {
                            "code": "validation_error",
                            "message": str(item),
                            "field": None,
                        }
                    )
            else:
                out.append(
                    {
                        "code": "validation_error",
                        "message": str(val),
                        "field": None,
                    }
                )
        elif isinstance(val, list):
            for item in val:
                out.append(
                    {
                        "code": "field_error",
                        "message": str(item),
                        "field": key,
                    }
                )
        elif isinstance(val, dict):
            for nk, nv in val.items():
                if isinstance(nv, list):
                    for item in nv:
                        out.append(
                            {
                                "code": "field_error",
                                "message": str(item),
                                "field": f"{key}.{nk}",
                            }
                        )
                else:
                    out.append(
                        {
                            "code": "field_error",
                            "message": str(nv),
                            "field": f"{key}.{nk}",
                        }
                    )
        else:
            out.append(
                {
                    "code": "field_error",
                    "message": str(val),
                    "field": key,
                }
            )
    return out
