"""
Confirms the local histogram model is the **primary** path for grading and that
the external vision APIs (OpenAI / Gemini) are only used as fallbacks.

These are pure-function tests — no DB / HTTP — so they run in <1 s and can be
cited as the academic guarantee that the on-server model is the default.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from apps.grading import grading_ai_service
from apps.grading.grading_ai_service import (
    DEFAULT_PREFER_API,
    PROVIDER_CHAIN_LOCAL_FIRST,
    suggest_grade_from_leaf_image,
)


def _png_bytes(rgb: tuple[int, int, int], size: tuple[int, int] = (160, 160)) -> bytes:
    im = Image.new("RGB", size, rgb)
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _leaf_like_png(size: tuple[int, int] = (200, 200)) -> bytes:
    """A small image with green-dominant pixels and enough texture to pass the gate."""
    im = Image.new("RGB", size, (30, 110, 40))
    px = im.load()
    # Add a checker pattern of a slightly different green so entropy is non-trivial.
    for y in range(size[1]):
        for x in range(size[0]):
            if (x + y) % 3 == 0:
                px[x, y] = (60, 145, 55)
            elif (x * y) % 7 == 0:
                px[x, y] = (40, 130, 35)
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_default_prefer_api_is_false():
    """The shipped default must be local-first."""
    assert DEFAULT_PREFER_API is False
    assert PROVIDER_CHAIN_LOCAL_FIRST[0] == "local_histogram_v1"


def test_local_first_is_used_when_local_succeeds(monkeypatch):
    """OpenAI/Gemini must NOT be invoked when the local model returns a valid result."""
    calls: list[str] = []

    def _boom_openai(**kwargs):
        calls.append("openai")
        raise AssertionError("OpenAI must not be called when local model succeeded")

    def _boom_gemini(**kwargs):
        calls.append("gemini")
        raise AssertionError("Gemini must not be called when local model succeeded")

    monkeypatch.setattr(grading_ai_service, "_openai_vision_suggest", _boom_openai)
    monkeypatch.setattr(grading_ai_service, "_gemini_vision_suggest", _boom_gemini)

    out = suggest_grade_from_leaf_image(
        image_bytes=_leaf_like_png(),
        mime_type="image/png",
    )
    assert out["provider"] == "local_histogram_v1"
    assert out["provider_chain"][0] == "local_histogram_v1"
    assert out["provider_chain_position"] == 0
    assert out["confidence"] <= 0.30, "Local path must hard-cap confidence at 0.30"
    assert "rgb_histogram_only" in out["hallucination_guards"]
    assert calls == [], "External vision APIs were called even though local succeeded"


def test_api_used_as_fallback_when_local_decode_fails(monkeypatch, settings):
    """If the local decoder explodes (corrupt bytes), the API must take over."""
    settings.OPENAI_API_KEY = "test-key"
    settings.GEMINI_API_KEY = ""

    def _fake_local_raise(image_bytes):
        raise RuntimeError("simulated Pillow decode failure")

    def _fake_openai(*, image_bytes, mime_type, context_lines):
        return {
            "suggested_grade": "B2",
            "confidence": 0.72,
            "alternates": ["B3"],
            "rationale": "fake openai vision result",
            "estimated_quality_score": 60.0,
            "estimated_moisture_percent": 14.0,
            "provider": "openai_vision",
            "model": "gpt-4o-mini",
        }

    monkeypatch.setattr(
        "apps.grading.local_leaf_histogram.suggest_grade_from_leaf_histogram",
        _fake_local_raise,
    )
    monkeypatch.setattr(grading_ai_service, "_openai_vision_suggest", _fake_openai)

    out = suggest_grade_from_leaf_image(
        image_bytes=b"\x00\x01garbage",
        mime_type="image/png",
    )
    assert out["provider"] == "openai_vision"
    assert out["provider_chain"][0] == "local_histogram_v1"
    assert out["provider_chain"].index("openai_vision") == 1
    assert any("local_histogram_v1_failed" in w for w in out["warnings"])


def test_prefer_api_true_uses_api_first(monkeypatch, settings):
    """Caller can opt into legacy API-first chain via prefer_api=True."""
    settings.OPENAI_API_KEY = "test-key"
    settings.GEMINI_API_KEY = ""
    seen_first: list[str] = []

    def _fake_openai(*, image_bytes, mime_type, context_lines):
        seen_first.append("openai")
        return {
            "suggested_grade": "C1",
            "confidence": 0.81,
            "alternates": [],
            "rationale": "api-first override",
            "estimated_quality_score": 65.0,
            "estimated_moisture_percent": 13.0,
            "provider": "openai_vision",
            "model": "gpt-4o-mini",
        }

    monkeypatch.setattr(grading_ai_service, "_openai_vision_suggest", _fake_openai)

    out = suggest_grade_from_leaf_image(
        image_bytes=_leaf_like_png(),
        mime_type="image/png",
        prefer_api=True,
    )
    assert seen_first == ["openai"], "prefer_api=True must put OpenAI first"
    assert out["provider"] == "openai_vision"
    assert out["provider_chain"][0] == "openai_vision"


def test_local_gate_refuses_non_leaf_without_calling_apis(monkeypatch):
    """Hard refusal on non-leaf images must NOT escalate to external APIs."""
    from apps.grading.grading_ai_service import NonTobaccoLeafError

    def _boom_openai(**kwargs):
        raise AssertionError("OpenAI must not be called when local gate already refused")

    def _boom_gemini(**kwargs):
        raise AssertionError("Gemini must not be called when local gate already refused")

    monkeypatch.setattr(grading_ai_service, "_openai_vision_suggest", _boom_openai)
    monkeypatch.setattr(grading_ai_service, "_gemini_vision_suggest", _boom_gemini)

    pure_grey = _png_bytes((128, 128, 128), size=(200, 200))
    raised = False
    try:
        suggest_grade_from_leaf_image(image_bytes=pure_grey, mime_type="image/png")
    except NonTobaccoLeafError:
        raised = True
    assert raised, "Local gate must refuse pure-grey images as non-leaf"
