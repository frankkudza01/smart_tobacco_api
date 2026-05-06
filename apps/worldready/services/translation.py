"""
Localized strings: code defaults + optional DB overrides per organization.
Locales: en (en_ZW), sn (Shona), nd (Ndebele).
"""
from __future__ import annotations

import re
from typing import Any

from apps.worldready.models import TranslationOverride

DEFAULT_STRINGS: dict[str, dict[str, str]] = {
    "menu.header": {
        "en": "Tobacco platform — choose:",
        "sn": "Nzvimbo yechirimwa — sarudza:",
        "nd": "Isikhungo setwayi — khetha:",
    },
    "menu.help": {
        "en": "Reply HELP for commands.",
        "sn": "Pindura HELP kuti uwane mirairo.",
        "nd": "Phendula HELP ukuze uthole imiyalo.",
    },
    "cmd.register_farm": {"en": "Register farm", "sn": "Nyoresa purazi", "nd": "Bhalisa ifama"},
    "cmd.create_lot": {"en": "Create lot", "sn": "Gadzira lot", "nd": "Dala ilothi"},
    "cmd.planting": {"en": "Log planting", "sn": "Nyora kudyara", "nd": "Bhala ukutshala"},
    "cmd.verify_doc": {"en": "Verify document", "sn": "Onganidza chinyorwa", "nd": "Qinisekisa idokhumenti"},
    "cmd.dispute": {"en": "Raise dispute", "sn": "Kumbira kukakavadzana", "nd": "Vula ingxabano"},
    "cmd.language": {"en": "Set language EN/SN/ND", "sn": "Sarudza mutauro EN/SN/ND", "nd": "Khetha ulimi EN/SN/ND"},
    "cmd.guided": {"en": "Guided mode ON/OFF", "sn": "Nzira yakadzikama ON/OFF", "nd": "Indlela elula ON/OFF"},
    "voice.received": {
        "en": "Voice received; processing…",
        "sn": "Izwi ratapirirwa…",
        "nd": "Lizwi lithathiwe…",
    },
    "privacy.no_pii_chain": {
        "en": "Only document hashes are anchored on-chain.",
        "sn": "Hash chete dzinonyorwa pachain.",
        "nd": "Kuphela ama-hash wedokhumenti ase-chain.",
    },
    "lang.set_ok": {
        "en": "Language set to {code}.",
        "sn": "Mutauro wakumiswa ku {code}.",
        "nd": "Ulimi lubekwe ku-{code}.",
    },
}


def _norm_lang(lang: str | None) -> str:
    if not lang:
        return "en"
    lang = lang.lower().strip()
    if lang.startswith("sn"):
        return "sn"
    if lang.startswith("nd"):
        return "nd"
    return "en"


def get_strings_for_locale(
    *,
    organization_id,
    lang: str,
) -> dict[str, str]:
    lang = _norm_lang(lang)
    out = {k: v.get(lang, v.get("en", k)) for k, v in DEFAULT_STRINGS.items()}
    if organization_id:
        overrides = TranslationOverride.objects.filter(
            organization_id=organization_id,
            locale__in=[lang, f"{lang}_ZW"],
        )
        for o in overrides:
            out[o.key] = o.value
    return out


def t(key: str, lang: str, organization_id=None, **vars: Any) -> str:
    lang = _norm_lang(lang)
    if organization_id:
        o = (
            TranslationOverride.objects.filter(organization_id=organization_id, key=key)
            .filter(locale__in=[lang, f"{lang}_ZW", "en", "en_ZW"])
            .order_by("-locale")
            .first()
        )
        if o:
            template = o.value
        else:
            template = DEFAULT_STRINGS.get(key, {}).get(lang) or DEFAULT_STRINGS.get(key, {}).get("en") or key
    else:
        template = DEFAULT_STRINGS.get(key, {}).get(lang) or DEFAULT_STRINGS.get(key, {}).get("en") or key
    for name, val in vars.items():
        template = re.sub(r"\{" + re.escape(name) + r"\}", str(val), template)
    return template


def resolve_whatsapp_language(contact) -> str:
    from apps.common.org_utils import get_user_primary_organization
    from apps.worldready.models import UserPreference

    if getattr(contact, "preferred_language", None):
        raw = contact.preferred_language
        if raw in ("sn", "nd", "en"):
            return raw
    user = contact.user
    if user:
        org = get_user_primary_organization(user)
        if org:
            pref = UserPreference.objects.filter(user=user, organization=org).first()
            if pref:
                return pref.preferred_language
    return "en"
