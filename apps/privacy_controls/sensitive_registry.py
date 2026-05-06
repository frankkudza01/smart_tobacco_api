"""
Field-level sensitivity classification for serializers and retention policy (code-enforced).
Format: "app_label.Model.field" -> metadata
"""
from __future__ import annotations

from apps.common.enums import UserRole

SENSITIVE_FIELD_REGISTRY: dict[str, dict] = {
    "accounts.FarmerProfile.national_id": {
        "classification": "PII_GOV_ID",
        "allowed_roles": (
            UserRole.SMALLHOLDER_FARMER,
            UserRole.REGULATOR_AUDITOR,
            UserRole.SYSTEM_ADMIN,
        ),
        "retention_years": 7,
        "mask_for_roles": (UserRole.BUYER_CONTRACTOR,),
    },
    "accounts.FarmerProfile.bank_account_number": {
        "classification": "FINANCIAL",
        "allowed_roles": (UserRole.SMALLHOLDER_FARMER, UserRole.SYSTEM_ADMIN),
        "retention_years": 7,
    },
    "accounts.FarmerProfile.mobile_money_number": {
        "classification": "PII_CONTACT",
        "allowed_roles": (
            UserRole.SMALLHOLDER_FARMER,
            UserRole.BUYER_CONTRACTOR,
            UserRole.REGULATOR_AUDITOR,
            UserRole.SYSTEM_ADMIN,
        ),
        "retention_years": 7,
    },
    "accounts.User.phone_number": {
        "classification": "PII_CONTACT",
        "allowed_roles": "__ALL__",
        "retention_years": 7,
    },
    "documents.Document.file": {
        "classification": "DOCUMENT_BINARY",
        "allowed_roles": "__SCOPE_BASED__",
        "never_log_raw": True,
    },
}
