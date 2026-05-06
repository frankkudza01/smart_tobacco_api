import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import FarmerProfile, BuyerProfile, AuditorProfile, AdminProfile
from apps.common.enums import UserRole
from apps.organizations.models import Organization, OrganizationMembership

User = get_user_model()
logger = logging.getLogger(__name__)

PROFILE_MODEL_MAP = {
    UserRole.SMALLHOLDER_FARMER: FarmerProfile,
    UserRole.BUYER_CONTRACTOR: BuyerProfile,
    UserRole.REGULATOR_AUDITOR: AuditorProfile,
    UserRole.SYSTEM_ADMIN: AdminProfile,
}


@transaction.atomic
def register_user(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: str = UserRole.SMALLHOLDER_FARMER,
    phone_number: str = "",
    profile_data: dict | None = None,
    skip_buyer_organization: bool = False,
) -> User:
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone_number=phone_number,
    )

    profile_model = PROFILE_MODEL_MAP.get(role)
    defaults = dict(profile_data or {})
    if role == UserRole.BUYER_CONTRACTOR:
        label = f"{first_name} {last_name}".strip() or email.split("@")[0]
        defaults.setdefault("company_name", label[:200])

    if profile_model:
        profile_model.objects.create(user=user, **defaults)

    if role == UserRole.BUYER_CONTRACTOR and not skip_buyer_organization:
        company = (defaults.get("company_name") or "").strip() or email.split("@")[0]
        base_name = f"{company} (Buyer)"
        org_name = base_name
        n = 0
        while Organization.objects.filter(name=org_name).exists():
            n += 1
            org_name = f"{base_name} #{n}"
        org = Organization.objects.create(name=org_name, org_type="contractor")
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role=UserRole.BUYER_CONTRACTOR,
            is_primary=True,
            is_active=True,
        )

    logger.info("User registered: %s with role %s", email, role)
    return user


def update_user_profile(user: User, data: dict) -> User:
    for field in ("first_name", "last_name", "phone_number"):
        if field in data:
            setattr(user, field, data[field])
    user.save(update_fields=["first_name", "last_name", "phone_number", "updated_at"])
    return user
