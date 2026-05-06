"""
LLM client wrapper (OpenAI/Gemini): timeouts, retries, circuit breaker, no secrets in prompts/logs.
"""
from __future__ import annotations

import json
import logging
import time
import base64
from typing import Any

from django.conf import settings
from django.core.cache import cache
import requests

logger = logging.getLogger(__name__)

CIRCUIT_KEY = "ai_llm_circuit_open_until"
_MISMATCH_WARNED = False
_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _retry_after_seconds(resp: requests.Response) -> float | None:
    """Parse Retry-After header (seconds). Returns None if missing or not numeric."""
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_gemini_error_response(resp: requests.Response) -> str:
    """Human-safe message; never includes API key or full URL."""
    code = resp.status_code
    try:
        data = resp.json()
        err = data.get("error")
        if isinstance(err, dict):
            msg = (err.get("message") or err.get("status") or "").strip()
            if msg:
                return f"Gemini API ({code}): {msg[:400]}"
    except Exception:
        pass
    return (
        f"Gemini API returned HTTP {code}. "
        "If this persists, verify GEMINI_API_KEY and AI_MODEL_NAME (e.g. gemini-2.0-flash or gemini-1.5-flash)."
    )


def _post_gemini_generate_content(
    *,
    model: str,
    api_key: str,
    payload: dict,
    timeout: float,
) -> dict:
    """POST generateContent with retries on transient errors. Raises RuntimeError on failure."""
    endpoint = _GEMINI_ENDPOINT.format(model=model)
    raw_max = int(getattr(settings, "AI_GEMINI_MAX_HTTP_RETRIES", 6) or 6)
    max_attempts = max(1, min(16, raw_max))
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            resp = requests.post(
                endpoint,
                params={"key": api_key},
                json=payload,
                timeout=timeout,
            )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                backoff = min(90.0, 0.75 * (2**attempt))
                ra = _retry_after_seconds(resp) if resp.status_code == 429 else None
                wait = max(backoff, ra or 0.0)
                if resp.status_code == 429:
                    wait = max(2.0, min(120.0, wait))
                else:
                    wait = max(0.5, min(30.0, wait))
                logger.warning(
                    "Gemini transient HTTP %s model=%s (attempt %s/%s), retry in %.1fs",
                    resp.status_code,
                    model,
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                raise RuntimeError(_parse_gemini_error_response(resp))
            return resp.json()
        except RuntimeError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = min(12.0, 0.5 * (2**attempt))
                logger.warning("Gemini request error %s; retry in %.1fs", exc, wait)
                time.sleep(wait)
                continue
            raise RuntimeError("Could not reach Gemini API (network error).") from exc
    if last_exc:
        raise RuntimeError("Could not reach Gemini API after retries.") from last_exc
    raise RuntimeError("Gemini request failed.")


def _gemini_models_to_try() -> list[str]:
    primary = (getattr(settings, "AI_MODEL_NAME", "") or "gemini-1.5-flash").strip()
    if not primary:
        primary = "gemini-1.5-flash"
    fb = (getattr(settings, "AI_GEMINI_FALLBACK_MODEL", "") or "").strip()
    out = [primary]
    if fb and fb.lower() != primary.lower():
        out.append(fb)
    return out


def _openai_model_name() -> str:
    configured = (getattr(settings, "AI_MODEL_NAME", "") or "").strip()
    if not configured:
        return "gpt-4o-mini"
    if configured.lower().startswith("gemini"):
        logger.warning(
            "AI_MODEL_NAME=%s is not an OpenAI model while AI_PROVIDER=openai; using gpt-4o-mini.",
            configured,
        )
        return "gpt-4o-mini"
    return configured


def _gemini_error_suggests_try_fallback_model(exc: BaseException) -> bool:
    """True when another Gemini model may succeed (capacity / transient)."""
    s = str(exc).lower()
    return any(
        m in s
        for m in (
            "503",
            "429",
            "500",
            "502",
            "504",
            "high demand",
            "overloaded",
            "try again",
            "unavailable",
            "resource exhausted",
            "deadline exceeded",
        )
    )


def _gemini_error_is_rate_limited(exc: BaseException) -> bool:
    s = str(exc).lower()
    return (
        "429" in s
        or "too many requests" in s
        or "resource exhausted" in s
        or ("rate" in s and "limit" in s)
    )


def _provider() -> str:
    global _MISMATCH_WARNED
    configured = (getattr(settings, "AI_PROVIDER", "openai") or "openai").strip().lower()
    model_name = (getattr(settings, "AI_MODEL_NAME", "") or "").strip().lower()
    if configured not in {"openai", "gemini"}:
        configured = "openai"
    if not _MISMATCH_WARNED:
        if model_name.startswith("gemini") and configured != "gemini":
            logger.warning(
                "AI provider/model mismatch at startup: AI_PROVIDER=%s but AI_MODEL_NAME=%s. "
                "Honoring AI_PROVIDER setting.",
                configured,
                model_name,
            )
            _MISMATCH_WARNED = True
        elif model_name.startswith("gpt") and configured == "gemini":
            logger.warning(
                "AI provider/model mismatch at startup: AI_PROVIDER=gemini but AI_MODEL_NAME=%s. "
                "Requests may fail unless model is switched to a Gemini model.",
                model_name,
            )
            _MISMATCH_WARNED = True
    return configured


def has_provider_credentials() -> bool:
    p = _provider()
    if p == "gemini":
        return bool(getattr(settings, "GEMINI_API_KEY", ""))
    return bool(getattr(settings, "OPENAI_API_KEY", ""))


def _circuit_fail():
    threshold = getattr(settings, "AI_CIRCUIT_BREAKER_THRESHOLD", 5)
    cooldown = getattr(settings, "AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS", 120)
    k = "ai_llm_fail_count"
    n = cache.get(k, 0) + 1
    cache.set(k, n, timeout=cooldown)
    if n >= threshold:
        cache.set(CIRCUIT_KEY, time.time() + cooldown, timeout=cooldown)
        logger.warning("LLM circuit opened after %s failures", n)


def _circuit_success():
    cache.delete("ai_llm_fail_count")
    cache.delete(CIRCUIT_KEY)


def circuit_is_open() -> bool:
    until = cache.get(CIRCUIT_KEY)
    if until is None:
        return False
    if time.time() < float(until):
        return True
    cache.delete(CIRCUIT_KEY)
    return False


def chat_json_schema(
    *,
    system_prompt: str,
    user_message: str,
    json_schema_name: str,
    json_schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Chat completion with JSON schema response. Raises on failure.
    """
    if circuit_is_open():
        raise RuntimeError("OpenAI circuit breaker is open; try again later.")

    # Gemini path currently uses prompt-constrained JSON output and post-parse.
    # OpenAI path still uses native response_format json_schema.
    if _provider() == "gemini":
        constrained = (
            f"{user_message}\n\n"
            "Return ONLY JSON matching this schema name and schema exactly.\n"
            f"schema_name={json_schema_name}\n"
            f"schema={json.dumps(json_schema, ensure_ascii=False)}"
        )
        content = chat_simple(system_prompt=system_prompt, user_message=constrained)
        try:
            return json.loads(content)
        except Exception as exc:
            raise RuntimeError(f"Gemini did not return valid JSON: {exc}") from exc

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    from openai import OpenAI

    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    max_retries = getattr(settings, "AI_OPENAI_MAX_RETRIES", 2)

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout, max_retries=max_retries)

    try:
        resp = client.chat.completions.create(
            model=_openai_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
            max_tokens=min(settings.AI_MAX_TOKENS, 4096),
        )
        content = resp.choices[0].message.content or "{}"
        out = json.loads(content)
        _circuit_success()
        return out
    except Exception:
        _circuit_fail()
        logger.exception("OpenAI chat_json_schema failed")
        raise


def chat_simple(
    *,
    system_prompt: str,
    user_message: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    """
    Optional ``prior_messages``: OpenAI-style turns before the final user message,
    each dict ``{"role": "user"|"assistant", "content": str}`` (no system entries).
    Used for multi-turn assistant threads.
    """
    if circuit_is_open():
        raise RuntimeError("LLM circuit breaker is open; try again later.")
    if not has_provider_credentials():
        p = _provider()
        if p == "gemini":
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    if _provider() == "gemini":
        return _chat_simple_gemini(
            system_prompt=system_prompt,
            user_message=user_message,
            prior_messages=prior_messages,
        )
    return _chat_simple_openai(
        system_prompt=system_prompt,
        user_message=user_message,
        prior_messages=prior_messages,
    )


def chat_with_image_simple(
    *,
    system_prompt: str,
    user_message: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> str:
    if circuit_is_open():
        raise RuntimeError("LLM circuit breaker is open; try again later.")
    if not has_provider_credentials():
        p = _provider()
        if p == "gemini":
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if _provider() == "gemini":
        return _chat_with_image_gemini(
            system_prompt=system_prompt,
            user_message=user_message,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
    return _chat_with_image_openai(
        system_prompt=system_prompt,
        user_message=user_message,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )


def _chat_simple_openai(
    *,
    system_prompt: str,
    user_message: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    from openai import OpenAI

    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout, max_retries=2)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in prior_messages or []:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    try:
        resp = client.chat.completions.create(
            model=_openai_model_name(),
            messages=messages,
            max_tokens=min(settings.AI_MAX_TOKENS, 4096),
        )
        text = (resp.choices[0].message.content or "").strip()
        _circuit_success()
        return text
    except Exception:
        _circuit_fail()
        logger.exception("OpenAI chat_simple failed")
        raise


def _chat_with_image_openai(
    *,
    system_prompt: str,
    user_message: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    from openai import OpenAI

    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout, max_retries=2)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64}"
    try:
        resp = client.chat.completions.create(
            model=_openai_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            max_tokens=min(settings.AI_MAX_TOKENS, 4096),
        )
        text = (resp.choices[0].message.content or "").strip()
        _circuit_success()
        return text
    except Exception:
        _circuit_fail()
        logger.exception("OpenAI chat_with_image failed")
        raise


def _gemini_transcript_from_prior(
    prior_messages: list[dict[str, str]] | None,
) -> str:
    if not prior_messages:
        return ""
    lines: list[str] = []
    for m in prior_messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        label = "Assistant" if role == "assistant" else "User"
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "Earlier in this conversation:\n" + "\n\n".join(lines) + "\n\n---\n"


def _chat_simple_gemini(
    *,
    system_prompt: str,
    user_message: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    models = _gemini_models_to_try()
    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    max_tokens = min(getattr(settings, "AI_MAX_TOKENS", 2048), 4096)
    prelude = _gemini_transcript_from_prior(prior_messages)
    combined = f"{prelude}{system_prompt}\n\n{user_message}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": combined}]},
        ],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
        },
    }
    last_exc: BaseException | None = None
    for mi, model in enumerate(models):
        try:
            data = _post_gemini_generate_content(
                model=model,
                api_key=api_key,
                payload=payload,
                timeout=float(timeout),
            )
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError("Gemini response has no candidates.")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join((p.get("text") or "") for p in parts).strip()
            if not text:
                raise RuntimeError("Gemini response text is empty.")
            _circuit_success()
            if mi > 0:
                logger.info("Gemini chat_simple succeeded on fallback model=%s", model)
            return text
        except RuntimeError as exc:
            last_exc = exc
            if mi < len(models) - 1 and _gemini_error_suggests_try_fallback_model(exc):
                logger.warning(
                    "Gemini chat_simple model=%s failed (%s); trying fallback model",
                    model,
                    exc,
                )
                continue
            _circuit_fail()
            if _gemini_error_is_rate_limited(exc):
                logger.warning(
                    "Gemini chat_simple rate-limited or exhausted after retries model=%s: %s",
                    model,
                    exc,
                )
            else:
                logger.exception("Gemini chat_simple failed model=%s", model)
            raise
        except Exception:
            _circuit_fail()
            logger.exception("Gemini chat_simple failed model=%s", model)
            raise
    assert last_exc is not None
    _circuit_fail()
    raise last_exc


def _chat_with_image_gemini(
    *,
    system_prompt: str,
    user_message: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    models = _gemini_models_to_try()
    timeout = getattr(settings, "AI_OPENAI_TIMEOUT_SECONDS", 45)
    max_tokens = min(getattr(settings, "AI_MAX_TOKENS", 2048), 4096)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"{system_prompt}\n\n{user_message}"},
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
            "temperature": 0.2,
        },
    }
    last_exc: BaseException | None = None
    for mi, model in enumerate(models):
        try:
            data = _post_gemini_generate_content(
                model=model,
                api_key=api_key,
                payload=payload,
                timeout=float(timeout),
            )
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError("Gemini response has no candidates.")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join((p.get("text") or "") for p in parts).strip()
            if not text:
                raise RuntimeError("Gemini response text is empty.")
            _circuit_success()
            if mi > 0:
                logger.info("Gemini chat_with_image succeeded on fallback model=%s", model)
            return text
        except RuntimeError as exc:
            last_exc = exc
            if mi < len(models) - 1 and _gemini_error_suggests_try_fallback_model(exc):
                logger.warning(
                    "Gemini chat_with_image model=%s failed (%s); trying fallback model",
                    model,
                    exc,
                )
                continue
            _circuit_fail()
            if _gemini_error_is_rate_limited(exc):
                logger.warning(
                    "Gemini chat_with_image rate-limited or exhausted after retries model=%s: %s",
                    model,
                    exc,
                )
            else:
                logger.exception("Gemini chat_with_image failed model=%s", model)
            raise
        except Exception:
            _circuit_fail()
            logger.exception("Gemini chat_with_image failed model=%s", model)
            raise
    assert last_exc is not None
    _circuit_fail()
    raise last_exc
