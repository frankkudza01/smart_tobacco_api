"""
Localized alert message templates (English first; keys for future Shona/Ndebele).
"""

from __future__ import annotations

from apps.tobacco_monitoring.models import TobaccoFieldPolygon


def _safe_lang(lang: str | None) -> str:
    v = (lang or "en").strip().lower()
    return v if v in {"en", "sn", "nd"} else "en"


def render_ndvi_drop_message(
    polygon: TobaccoFieldPolygon,
    *,
    pct_drop: float,
    lang: str = "en",
    recipient_kind: str = "farmer",
) -> str:
    province = polygon.province or "your region"
    field = polygon.field_name or "your registered field"
    lang = _safe_lang(lang)
    rk = (recipient_kind or "farmer").strip().lower()
    if lang == "sn":
        if rk == "buyer":
            return (
                f"Yambiro: Munda wakabatana newe \"{field}\" mu{province} waratidza kuderera kweNDVI "
                f"ne {pct_drop:.1f}%. Batsirana nemurimi kuti aongorore minda nekukurumidza."
            )
        return (
            f"Yambiro: Munda wako wefodya \"{field}\" mu{province} waratidza kuderera kwehutano hwemashizha "
            f"ne {pct_drop:.1f}% kubva pakupfuura kwesatelliti. Ongorora minda nhasi."
        )
    if lang == "nd":
        if rk == "buyer":
            return (
                f"Isixwayiso: Insimu exhumene lawe \"{field}\" e{province} itshengise ukwehla kweNDVI "
                f"ngo {pct_drop:.1f}%. Xhumana lomlimi enze ukuhlola masinya."
            )
        return (
            f"Isixwayiso: Insimu yakho kagwayi \"{field}\" e{province} itshengise ukwehla kwezihlahla "
            f"ngo {pct_drop:.1f}% kusukela kudatha yesathelayithi yokucina. Hlola insimu namhlanje."
        )
    if rk == "buyer":
        return (
            f"Alert: A contracted tobacco field \"{field}\" in {province} shows an NDVI drop of "
            f"{pct_drop:.1f}%. Please coordinate an immediate farm check with the grower."
        )
    return (
        f"Alert: Your tobacco field \"{field}\" in {province} shows a drop in vegetation "
        f"health of about {pct_drop:.1f}% since the last satellite pass. "
        "Please scout the field today for pests, disease, nutrient stress, or moisture problems."
    )


def render_moisture_stress_message(
    polygon: TobaccoFieldPolygon,
    *,
    moisture_value: float,
    drop_pct: float,
    lang: str = "en",
    recipient_kind: str = "farmer",
) -> str:
    province = polygon.province or "your region"
    field = polygon.field_name or "your registered field"
    lang = _safe_lang(lang)
    rk = (recipient_kind or "farmer").strip().lower()
    if lang == "sn":
        if rk == "buyer":
            return (
                f"Yambiro: Munda wakabatana newe \"{field}\" mu{province} une stress yemvura "
                f"(moisture {moisture_value:.3f}, kuderera {drop_pct:.1f}%). Batsirana nemurimi kuti atore matanho."
            )
        return (
            f"Yambiro: Munda wako \"{field}\" mu{province} une kushomeka kwemvura "
            f"(moisture {moisture_value:.3f}, kuderera {drop_pct:.1f}%). Tarisa kudiridza nekuchengetedza hunyoro."
        )
    if lang == "nd":
        if rk == "buyer":
            return (
                f"Isixwayiso: Insimu exhumene lawe \"{field}\" e{province} itshengisa ukuswela umswakama "
                f"(moisture {moisture_value:.3f}, ukwehla {drop_pct:.1f}%). Xhumana lomlimi masinya."
            )
        return (
            f"Isixwayiso: Insimu yakho \"{field}\" e{province} itshengisa ukuswela umswakama "
            f"(moisture {moisture_value:.3f}, ukwehla {drop_pct:.1f}%). Hlola ukuchelela lokubamba umswakama."
        )
    if rk == "buyer":
        return (
            f"Alert: A contracted tobacco field \"{field}\" in {province} is showing moisture stress "
            f"(index {moisture_value:.3f}, drop {drop_pct:.1f}%). Coordinate immediate intervention."
        )
    return (
        f"Alert: Your tobacco field \"{field}\" in {province} shows moisture stress "
        f"(index {moisture_value:.3f}, drop {drop_pct:.1f}%). "
        "Please inspect irrigation, mulching, and root-zone moisture urgently."
    )


def render_ndvi_drop_generic(polygon: TobaccoFieldPolygon) -> str:
    return (
        "Warning: We detected unexpected tobacco crop stress in your registered field "
        f"\"{polygon.field_name}\". Please inspect this area today for pests, disease, "
        "nutrient stress, or moisture problems."
    )
