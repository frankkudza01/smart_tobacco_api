"""
Tobacco grade suggestion for leaf photographs.

**Provider order (default, per-supervisor requirement):**
``local_histogram_v1`` → ``openai_vision`` → ``gemini_vision``.

The local on-server histogram model is the **primary** path so the platform can
operate fully on-premise and demonstrate an explicitly trained / clamped local
model. External vision APIs are consulted **only as fallbacks** when the local
model raises a non-validation exception or when the caller explicitly opts in
with ``prefer_api=True``.

Does not use the global LLM circuit breaker so transient API failures never
block local grading.
"""
from __future__ import annotations

import base64
import difflib
import json
import logging
import re
from typing import Any

import requests
from django.conf import settings

from apps.ai_intelligence.services.openai_safe import _parse_gemini_error_response
from apps.grading.zimbabwe_grades import ALLOWED_GRADES, GRADES_VERSION, allowed_grades_sorted

logger = logging.getLogger(__name__)


class NonTobaccoLeafError(ValueError):
    """Raised when an uploaded image is not tobacco leaf material."""


_GRADE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "suggested_grade": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "alternates": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "rationale": {"type": "string"},
        "estimated_quality_score": {"type": "number", "minimum": 0, "maximum": 100},
        "estimated_moisture_percent": {"type": "number", "minimum": 0, "maximum": 100},
        "is_tobacco_leaf": {"type": "boolean"},
        "subject_label": {"type": "string"},
    },
    "required": [
        "suggested_grade",
        "confidence",
        "alternates",
        "rationale",
        "estimated_quality_score",
        "estimated_moisture_percent",
        "is_tobacco_leaf",
        "subject_label",
    ],
}


def _vision_model_openai() -> str:
    return (getattr(settings, "AI_VISION_MODEL_NAME", None) or settings.AI_MODEL_NAME or "gpt-4o-mini").strip()


def _gemini_model() -> str:
    m = (getattr(settings, "AI_MODEL_NAME", None) or "").strip()
    if m and m.lower().startswith("gemini"):
        return m
    # Keep grading fallback independent from global OpenAI model naming.
    return "gemini-2.5-flash"


def _gemini_models_to_try() -> list[str]:
    primary = _gemini_model()
    # Prefer currently supported modern Gemini models for v1beta generateContent.
    defaults = ["gemini-2.5-flash", "gemini-2.0-flash"]
    out: list[str] = []
    for model in [primary, *defaults]:
        key = model.strip()
        if key and key not in out:
            out.append(key)
    return out


def _snap_to_allowed(raw: str | None, alternates: list[str] | None) -> str:
    allowed_list = list(ALLOWED_GRADES)
    for candidate in [raw, *(alternates or [])]:
        if not candidate:
            continue
        x = str(candidate).strip().upper().replace(" ", "")
        x = re.sub(r"[^A-Z0-9]", "", x)
        if x in ALLOWED_GRADES:
            return x
        close = difflib.get_close_matches(x, allowed_list, n=1, cutoff=0.55)
        if close:
            return close[0]
    return "C2"


def _heuristic_grade(moisture_percent: float | None) -> tuple[str, float, str]:
    """Last-resort suggestion when no vision LLM succeeds."""
    if moisture_percent is not None and moisture_percent > 20.0:
        return "X2", 0.12, "High moisture band — manual inspection required; placeholder reject-band code."
    if moisture_percent is not None and moisture_percent > 17.0:
        return "L2", 0.15, "Elevated moisture — tentative mid-strip suggestion for human review."
    return "B2", 0.1, "No vision model output; neutral mid-ladder placeholder for human review."


def _clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def _fallback_estimates(
    *,
    confidence: float,
    moisture_percent: float | None,
) -> tuple[float, float]:
    # Conservative fallback estimates when provider doesn't emit image-derived metrics.
    moisture = moisture_percent if moisture_percent is not None else 14.0
    quality = 45.0 + (confidence * 35.0)
    return _clamp(quality, 0.0, 100.0), _clamp(moisture, 0.0, 100.0)


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _is_tobacco_leaf_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _ensure_tobacco_leaf_or_raise(*, payload: dict[str, Any], provider: str) -> None:
    is_tobacco = _is_tobacco_leaf_flag(payload.get("is_tobacco_leaf"))
    label = str(payload.get("subject_label") or "").strip() or "unknown"
    if not is_tobacco:
        raise NonTobaccoLeafError(
            f"Image rejected by {provider}: subject '{label}' is not a tobacco leaf/strip."
        )


def _openai_vision_suggest(
    *,
    image_bytes: bytes,
    mime_type: str,
    context_lines: list[str],
) -> dict[str, Any]:
    if not getattr(settings, "OPENAI_API_KEY", ""):
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI

    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    max_retries = getattr(settings, "AI_OPENAI_MAX_RETRIES", 2)
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout, max_retries=max_retries)
    model = _vision_model_openai()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64}"

    catalogue = ", ".join(allowed_grades_sorted()[:120])
    if len(allowed_grades_sorted()) > 120:
        catalogue += ", …"

    system = (
        "You are a tobacco grading assistant for Zimbabwe flue-cured auction-style codes. "
        "First determine if the image is a tobacco leaf/strip suitable for grading. "
        "If image is another crop/object/person/scene or unclear, set is_tobacco_leaf=false and set subject_label. "
        "You must ONLY output grades from the allowed catalogue (strict JSON schema). "
        "Be conservative: if uncertain, lower confidence and list alternates. "
        "Do not invent codes outside the schema. Colour/body/strip position cues may inform the letter group. "
        "Also estimate quality_score (0-100) and moisture_percent (0-100) from visible image characteristics."
    )
    user_text = (
        "Analyse this tobacco leaf/strip photograph and suggest the best-matching official-style grade.\n"
        + "\n".join(context_lines)
        + "\n\nAllowed grade codes include: "
        + catalogue
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "tobacco_grade_suggestion",
                "schema": _GRADE_JSON_SCHEMA,
                "strict": True,
            },
        },
        max_completion_tokens=min(getattr(settings, "AI_MAX_TOKENS", 2048), 4096),
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)
    _ensure_tobacco_leaf_or_raise(payload=data, provider="openai_vision")
    primary = _snap_to_allowed(data.get("suggested_grade"), data.get("alternates") if isinstance(data.get("alternates"), list) else [])
    alts = [a for a in (data.get("alternates") or []) if isinstance(a, str)]
    alts_snapped = []
    for a in alts:
        s = _snap_to_allowed(a, [])
        if s != primary and s not in alts_snapped:
            alts_snapped.append(s)
    conf = float(data.get("confidence") or 0.5)
    conf = max(0.0, min(1.0, conf))
    quality, moisture = _fallback_estimates(
        confidence=conf,
        moisture_percent=None,
    )
    if data.get("estimated_quality_score") is not None:
        quality = _clamp(float(data.get("estimated_quality_score") or quality), 0.0, 100.0)
    if data.get("estimated_moisture_percent") is not None:
        moisture = _clamp(float(data.get("estimated_moisture_percent") or moisture), 0.0, 100.0)
    return {
        "suggested_grade": primary,
        "confidence": conf,
        "alternates": alts_snapped[:5],
        "rationale": str(data.get("rationale") or "").strip() or "Vision model classification.",
        "estimated_quality_score": round(quality, 1),
        "estimated_moisture_percent": round(moisture, 1),
        "provider": "openai_vision",
        "model": model,
        "hallucination_guards": [
            "json_schema_strict",
            "is_tobacco_leaf_check",
            "allowed_grades_snap",
            "confidence_clamped_0_to_1",
            "quality_moisture_clamped_0_to_100",
            "alternates_snapped_or_dropped",
        ],
    }


def _gemini_vision_suggest(
    *,
    image_bytes: bytes,
    mime_type: str,
    context_lines: list[str],
) -> dict[str, Any]:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    models_to_try = _gemini_models_to_try()
    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    max_tokens = min(getattr(settings, "AI_MAX_TOKENS", 2048), 4096)

    catalogue = ", ".join(allowed_grades_sorted()[:100])
    prompt = (
        "You are a Zimbabwe tobacco grading assistant. Return ONLY valid JSON with keys "
        "suggested_grade, confidence (0-1), alternates (array of strings, max 5), rationale, "
        "estimated_quality_score (0-100), estimated_moisture_percent (0-100), "
        "is_tobacco_leaf (boolean), subject_label (string). "
        "If image is not a tobacco leaf/strip or is unclear, set is_tobacco_leaf=false and subject_label accordingly. "
        "suggested_grade MUST be one of the allowed codes.\n"
        + "\n".join(context_lines)
        + f"\n\nAllowed codes (sample): {catalogue}\n"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ],
            },
        ],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.15,
        },
    }
    data: dict[str, Any] | None = None
    used_model: str | None = None
    last_error: RuntimeError | None = None
    for model in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = requests.post(endpoint, params={"key": api_key}, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            err = RuntimeError(_parse_gemini_error_response(resp))
            last_error = err
            logger.info("Gemini grading model=%s failed: %s", model, err)
            continue
        data = resp.json()
        used_model = model
        break
    if data is None:
        assert last_error is not None
        raise last_error
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini: no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join((p.get("text") or "") for p in parts).strip()
    parsed = _parse_json_loose(text)
    _ensure_tobacco_leaf_or_raise(payload=parsed, provider="gemini_vision")
    primary = _snap_to_allowed(parsed.get("suggested_grade"), parsed.get("alternates") if isinstance(parsed.get("alternates"), list) else [])
    alts_raw = parsed.get("alternates") if isinstance(parsed.get("alternates"), list) else []
    alts_snapped = []
    for a in alts_raw:
        if isinstance(a, str):
            s = _snap_to_allowed(a, [])
            if s != primary and s not in alts_snapped:
                alts_snapped.append(s)
    conf = float(parsed.get("confidence") or 0.45)
    conf = max(0.0, min(1.0, conf))
    quality, moisture = _fallback_estimates(
        confidence=conf,
        moisture_percent=None,
    )
    if parsed.get("estimated_quality_score") is not None:
        quality = _clamp(float(parsed.get("estimated_quality_score") or quality), 0.0, 100.0)
    if parsed.get("estimated_moisture_percent") is not None:
        moisture = _clamp(float(parsed.get("estimated_moisture_percent") or moisture), 0.0, 100.0)
    return {
        "suggested_grade": primary,
        "confidence": conf,
        "alternates": alts_snapped[:5],
        "rationale": str(parsed.get("rationale") or "").strip() or "Gemini vision classification.",
        "estimated_quality_score": round(quality, 1),
        "estimated_moisture_percent": round(moisture, 1),
        "provider": "gemini_vision",
        "model": used_model,
        "hallucination_guards": [
            "json_loose_parse",
            "is_tobacco_leaf_check",
            "allowed_grades_snap",
            "confidence_clamped_0_to_1",
            "quality_moisture_clamped_0_to_100",
            "alternates_snapped_or_dropped",
        ],
    }


PROVIDER_CHAIN_LOCAL_FIRST = [
    "local_histogram_v1",
    "openai_vision",
    "gemini_vision",
]

# When True, callers can request the higher-confidence vision LLMs first
# (e.g. an explicit ``prefer_api=true`` form field). Defaults to False so the
# **local model is the primary path** and the API is only a fallback —
# this is the academic / on-premise contract demanded by the supervisor.
DEFAULT_PREFER_API = False


def _suggest_local_only_with_optional_remote_prompt(
    *,
    image_bytes: bytes,
    warnings: list[str],
) -> dict[str, Any]:
    """
    Run only the local histogram path.

    On success, returns the usual suggestion payload. On unexpected failure,
    returns ``needs_remote_fallback: True`` so the client can ask the user
    before spending cloud API quota. ``NotALeafImageError`` is re-raised as
    [NonTobaccoLeafError] (no cloud fallback for obvious non-leaf images).
    """
    from apps.grading.local_leaf_histogram import (
        NotALeafImageError,
        suggest_grade_from_leaf_histogram,
    )

    try:
        out = suggest_grade_from_leaf_histogram(image_bytes)
    except NotALeafImageError as exc:
        raise NonTobaccoLeafError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface to client for confirm-then-API
        w = list(warnings) + [f"local_histogram_v1_failed: {exc}"]
        return {
            "needs_remote_fallback": True,
            "fallback_reason": str(exc),
            "warnings": w,
            "suggested_grade": "",
            "confidence": 0.0,
            "alternates": [],
            "rationale": "",
            "provider": "none",
            "model": None,
            "allowed_grades_version": GRADES_VERSION,
            "provider_chain": ["local_histogram_v1"],
            "provider_chain_position": 0,
            "hallucination_guards": [],
        }
    out["allowed_grades_version"] = GRADES_VERSION
    out["warnings"] = list(warnings)
    out["provider_chain"] = ["local_histogram_v1"]
    out["provider_chain_position"] = 0
    return out


def suggest_grade_from_leaf_image(
    *,
    image_bytes: bytes,
    mime_type: str,
    lot_number: str | None = None,
    tobacco_type: str | None = None,
    moisture_percent: float | None = None,
    prefer_api: bool = DEFAULT_PREFER_API,
    defer_remote_fallback: bool = False,
) -> dict[str, Any]:
    """
    Suggest a Zimbabwe-style flue-cured grade for a leaf photograph.

    **Provider order (default):** local histogram → OpenAI vision → Gemini vision.

    The local model is the primary path so the system can run on-premise and we
    can defend the accuracy of an explicitly trained / clamped on-server model.
    External vision APIs are only consulted when the local path either:

    - raises a non-validation exception (image decode error, etc.), or
    - is bypassed by ``prefer_api=True`` from the caller.

    The local **tobacco-likeness gate** still refuses obvious non-leaf photos by
    raising ``NonTobaccoLeafError`` *without* burning external API quota.

    If ``defer_remote_fallback`` is True, only the local histogram is run. If it
    fails with an unexpected error, the response is a JSON dict with
    ``needs_remote_fallback: True`` (HTTP 200) so the app can confirm before
    calling again with ``prefer_api`` or a second pass without ``defer``.

    The response always carries:

    - ``provider``: which model produced the answer.
    - ``provider_chain``: the ordered list of providers that were considered,
      so the API consumer can see "local first, API as fallback" at runtime.
    - ``hallucination_guards``: documented constraints applied to the response.
    """
    warnings: list[str] = []
    ctx: list[str] = []
    if lot_number:
        ctx.append(f"Lot number (context): {lot_number}")
    if tobacco_type:
        ctx.append(f"Tobacco type (context): {tobacco_type}")
    if moisture_percent is not None:
        ctx.append(f"Reported moisture % (context): {moisture_percent}")

    if defer_remote_fallback:
        if prefer_api:
            warnings.append("prefer_api_ignored_because_defer_remote_fallback")
        return _suggest_local_only_with_optional_remote_prompt(
            image_bytes=image_bytes,
            warnings=warnings,
        )

    if prefer_api:
        order = ["openai_vision", "gemini_vision", "local_histogram_v1"]
    else:
        order = list(PROVIDER_CHAIN_LOCAL_FIRST)

    for provider in order:
        try:
            if provider == "local_histogram_v1":
                from apps.grading.local_leaf_histogram import (
                    NotALeafImageError,
                    suggest_grade_from_leaf_histogram,
                )

                try:
                    out = suggest_grade_from_leaf_histogram(image_bytes)
                except NotALeafImageError as exc:
                    # Gate rejection is a hard refusal — do NOT fall through to
                    # external vision APIs (no point burning quota on a non-leaf
                    # photo we already rejected with high confidence).
                    raise NonTobaccoLeafError(str(exc)) from exc
                out["allowed_grades_version"] = GRADES_VERSION
                out["warnings"] = warnings
                out["provider_chain"] = order
                out["provider_chain_position"] = order.index(provider)
                return out

            if provider == "openai_vision":
                if not getattr(settings, "OPENAI_API_KEY", ""):
                    warnings.append("openai_vision_skipped_no_api_key")
                    continue
                out = _openai_vision_suggest(
                    image_bytes=image_bytes, mime_type=mime_type, context_lines=ctx
                )
                out["allowed_grades_version"] = GRADES_VERSION
                out["warnings"] = warnings
                out["provider_chain"] = order
                out["provider_chain_position"] = order.index(provider)
                return out

            if provider == "gemini_vision":
                if not getattr(settings, "GEMINI_API_KEY", ""):
                    warnings.append("gemini_vision_skipped_no_api_key")
                    continue
                out = _gemini_vision_suggest(
                    image_bytes=image_bytes, mime_type=mime_type, context_lines=ctx
                )
                out["allowed_grades_version"] = GRADES_VERSION
                out["warnings"] = warnings
                out["provider_chain"] = order
                out["provider_chain_position"] = order.index(provider)
                return out
        except NonTobaccoLeafError:
            raise
        except Exception as exc:
            warnings.append(f"{provider}_failed: {exc}")
            logger.info(
                "Grading provider %s failed, trying next in chain: %s",
                provider,
                exc,
            )
            continue

    raise RuntimeError(
        "All grading providers (local + vision APIs) failed. "
        f"Tried in order: {order}. Last warnings: {warnings[-3:]}"
    )
