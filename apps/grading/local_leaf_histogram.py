"""
Local (on-server) leaf image analysis: RGB histogram + tobacco-likeness gate.

This is intentionally lightweight (Pillow only). It exists for two reasons:

1. **Resilience**: keep grading usable when external vision APIs are down.
2. **Hallucination guards** (academic):
   - Confidence is **hard-capped** — the local path NEVER claims more than 0.30 confidence,
     because no vision model is being run. Downstream UIs surface this clearly.
   - Tobacco-likeness gate: rejects images that obviously aren't a leaf/strip
     (very small images, near-uniform colour fields, or no green/yellow band).
   - All numeric fields are clamped to documented ranges; the response includes a
     ``hallucination_guards`` array listing every constraint applied so the
     answer is auditable.
"""
from __future__ import annotations

import math
from io import BytesIO

from PIL import Image, ImageStat


class NotALeafImageError(ValueError):
    """Raised when the image fails the local tobacco-likeness gate."""


_MIN_DIM_PX = 80
_MAX_LOCAL_CONFIDENCE = 0.30
_LOCAL_GUARDS = [
    "rgb_histogram_only",
    "confidence_capped_0_30",
    "moisture_clamped_10_to_24_percent",
    "quality_clamped_15_to_92",
    "tobacco_likeness_gate",
    "no_external_llm_call",
]


def _heuristic_grade_from_moisture(moisture_percent: float) -> tuple[str, float, str]:
    if moisture_percent > 20.0:
        return "X2", 0.10, "High moisture band — manual inspection required."
    if moisture_percent > 17.0:
        return "L2", 0.14, "Elevated moisture — tentative mid-strip suggestion."
    return "B2", 0.10, "Neutral mid-ladder placeholder for human review."


def _shannon_entropy_8bit(channel_values: list[int]) -> float:
    counts: dict[int, int] = {}
    for v in channel_values:
        counts[v] = counts.get(v, 0) + 1
    total = float(len(channel_values)) or 1.0
    h = 0.0
    for c in counts.values():
        p = c / total
        if p > 0:
            h -= p * math.log2(p)
    return h  # 0..8 for 8-bit data


def _tobacco_likeness_check(im: Image.Image) -> dict:
    """
    Cheap heuristics rejecting obviously-not-a-leaf images.

    Returns ``{"ok": bool, "reasons": [..]}``. We do NOT claim this proves the image
    *is* tobacco — only that it has plausibly leaf-like statistics.
    """
    w, h = im.size
    reasons: list[str] = []
    if min(w, h) < _MIN_DIM_PX:
        reasons.append(f"image_too_small (<{_MIN_DIM_PX}px on shortest side)")
    pixels = list(im.getdata())
    if not pixels:
        reasons.append("empty_image")
        return {"ok": False, "reasons": reasons}
    n = len(pixels)
    r_vals = [p[0] for p in pixels]
    g_vals = [p[1] for p in pixels]
    b_vals = [p[2] for p in pixels]

    # Channel entropy — uniform fills (a black/white square) have very low entropy.
    sample = pixels[::max(1, n // 4096)]
    sample_rgb_avg = [int((p[0] + p[1] + p[2]) / 3) for p in sample]
    entropy = _shannon_entropy_8bit(sample_rgb_avg)
    if entropy < 3.5:
        reasons.append(f"low_entropy_uniform_field (H={entropy:.2f})")

    # Foliage / cured-leaf cue: at least a meaningful band of pixels in a green or
    # yellow-brown range. This is **not** species recognition; it's "looks like vegetation".
    leaflike = 0
    for r, g, b in zip(r_vals, g_vals, b_vals, strict=True):
        # green dominance OR warm ochre (cured leaf) range
        green_dom = g > r and g >= b and (g - min(r, b)) > 10
        ochre = 110 <= r <= 220 and 90 <= g <= 200 and b < g and (r - b) > 25
        if green_dom or ochre:
            leaflike += 1
    leaflike_ratio = leaflike / n
    if leaflike_ratio < 0.10:
        reasons.append(f"insufficient_leaflike_pixels ({leaflike_ratio*100:.1f}%)")

    return {
        "ok": not reasons,
        "reasons": reasons,
        "leaflike_ratio": round(leaflike_ratio, 4),
        "entropy": round(entropy, 3),
    }


def suggest_grade_from_leaf_histogram(image_bytes: bytes) -> dict:
    """
    Compute a low-confidence grade suggestion from RGB statistics + a moisture proxy.

    Raises ``NotALeafImageError`` when the tobacco-likeness gate fails so the caller
    can surface a clear "upload a leaf photo" message instead of producing a number.
    """
    try:
        im = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise NotALeafImageError(f"Image could not be decoded: {exc}") from exc
    im.thumbnail((384, 384))

    gate = _tobacco_likeness_check(im)
    if not gate["ok"]:
        raise NotALeafImageError(
            "Local tobacco-likeness gate rejected the image: "
            + "; ".join(gate["reasons"])
        )

    stat = ImageStat.Stat(im)
    mean_r, mean_g, mean_b = stat.mean[0], stat.mean[1], stat.mean[2]
    std_r, std_g, std_b = stat.stddev[0], stat.stddev[1], stat.stddev[2]
    brightness = (mean_r + mean_g + mean_b) / 3.0
    texture = (std_r + std_g + std_b) / 3.0

    # Empirical proxy: darker, higher-variance strips correlate with wetter visual bands.
    moisture = 11.5 + (120.0 - brightness) / 18.0 + min(texture / 10.0, 6.5)
    moisture = max(10.0, min(24.0, moisture))
    grade, raw_conf, rationale = _heuristic_grade_from_moisture(moisture)
    quality = max(15.0, min(92.0, 48.0 + (brightness - 90.0) / 6.0 - moisture))
    confidence = min(_MAX_LOCAL_CONFIDENCE, max(0.05, raw_conf))

    return {
        "suggested_grade": grade,
        "confidence": round(confidence, 3),
        "alternates": [],
        "rationale": (
            f"{rationale} Local histogram model: brightness={brightness:.1f}, "
            f"textureσ={texture:.1f}; moisture_proxy={moisture:.1f}%."
        ),
        "estimated_quality_score": round(quality, 1),
        "estimated_moisture_percent": round(moisture, 1),
        "provider": "local_histogram_v1",
        "model": "rgb_hist_moisture_proxy",
        "low_confidence_local": True,
        "hallucination_guards": list(_LOCAL_GUARDS),
        "tobacco_likeness": {
            "leaflike_ratio": gate["leaflike_ratio"],
            "entropy": gate["entropy"],
        },
    }
