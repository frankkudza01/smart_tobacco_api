import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.common.enums import UserRole
from apps.common.models import BaseModel


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", UserRole.SYSTEM_ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True, default="")
    role = models.CharField(max_length=30, choices=UserRole.choices, default=UserRole.SMALLHOLDER_FARMER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class FarmerProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="farmer_profile")
    national_id = models.CharField(max_length=50, unique=True)
    district = models.CharField(max_length=100, blank=True, default="")
    ward = models.CharField(max_length=100, blank=True, default="")
    village = models.CharField(max_length=100, blank=True, default="")
    bank_name = models.CharField(max_length=100, blank=True, default="")
    bank_account_number = models.CharField(max_length=50, blank=True, default="")
    mobile_money_number = models.CharField(max_length=20, blank=True, default="")
    years_of_experience = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "accounts_farmer_profile"

    def __str__(self):
        return f"Farmer: {self.user.full_name}"


class BuyerProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="buyer_profile")
    company_name = models.CharField(max_length=200)
    license_number = models.CharField(max_length=100, blank=True, default="")
    buyer_type = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "accounts_buyer_profile"

    def __str__(self):
        return f"Buyer: {self.company_name}"


class AuditorProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="auditor_profile")
    department = models.CharField(max_length=200, blank=True, default="")
    badge_number = models.CharField(max_length=50, blank=True, default="")
    jurisdiction = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "accounts_auditor_profile"

    def __str__(self):
        return f"Auditor: {self.user.full_name}"


class AdminProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_profile")
    department = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "accounts_admin_profile"

    def __str__(self):
        return f"Admin: {self.user.full_name}"


class OTPChallengeLog(BaseModel):
    """Audit log for OTP lifecycle. OTP code is NEVER stored here — Redis is the source of truth."""

    phone_number = models.CharField(max_length=20, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="otp_challenges")
    purpose = models.CharField(max_length=30, choices=[
        ("LOGIN", "Login"),
        ("REGISTRATION", "Registration"),
        ("PASSWORD_RESET", "Password Reset"),
    ], default="LOGIN")
    status = models.CharField(max_length=20, choices=[
        ("PENDING", "Pending"),
        ("VERIFIED", "Verified"),
        ("EXPIRED", "Expired"),
        ("MAX_ATTEMPTS", "Max Attempts Exceeded"),
    ], default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    delivery_channel = models.CharField(max_length=20, default="whatsapp")
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "accounts_otp_challenge_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number", "status"]),
        ]

    def __str__(self):
        return f"OTP {self.purpose} for {self.phone_number} ({self.status})"
