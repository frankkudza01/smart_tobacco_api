from django.db import models


class UserRole(models.TextChoices):
    SMALLHOLDER_FARMER = "SMALLHOLDER_FARMER", "Smallholder Farmer"
    BUYER_CONTRACTOR = "BUYER_CONTRACTOR", "Buyer / Contractor"
    REGULATOR_AUDITOR = "REGULATOR_AUDITOR", "Regulator / Auditor"
    SYSTEM_ADMIN = "SYSTEM_ADMIN", "System Admin"


class FarmGisVerificationStatus(models.TextChoices):
    """Auditor / regulator review of farmer-submitted farm boundary (GIS)."""

    PENDING = "PENDING", "Pending review"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"


class LotStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REGISTERED = "REGISTERED", "Registered"
    IN_CURING = "IN_CURING", "In Curing"
    CURED = "CURED", "Cured"
    GRADED = "GRADED", "Graded"
    LISTED_FOR_SALE = "LISTED_FOR_SALE", "Listed for Sale"
    SOLD = "SOLD", "Sold"
    SETTLED = "SETTLED", "Settled"
    DISPUTED = "DISPUTED", "Disputed"


class TraceEventType(models.TextChoices):
    PLANTING = "PLANTING", "Planting"
    FERTILIZING = "FERTILIZING", "Fertilizing"
    HARVESTING = "HARVESTING", "Harvesting"
    CURING = "CURING", "Curing"
    STORAGE = "STORAGE", "Storage"
    TRANSPORT = "TRANSPORT", "Transport"
    GRADING = "GRADING", "Grading"
    SALE = "SALE", "Sale"
    DELIVERY = "DELIVERY", "Delivery"
    INSPECTION = "INSPECTION", "Inspection"
    OTHER = "OTHER", "Other"


class DocumentType(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    CERTIFICATE = "CERTIFICATE", "Certificate"
    GRADING_SHEET = "GRADING_SHEET", "Grading Sheet"
    DELIVERY_NOTE = "DELIVERY_NOTE", "Delivery Note"
    INSPECTION_RECORD = "INSPECTION_RECORD", "Inspection Record"
    PROOF_OF_PAYMENT = "PROOF_OF_PAYMENT", "Proof of Payment"
    DISPUTE_EVIDENCE = "DISPUTE_EVIDENCE", "Dispute Evidence"
    OTHER = "OTHER", "Other"


class SaleType(models.TextChoices):
    AUCTION = "AUCTION", "Auction"
    DIRECT = "DIRECT", "Direct Contract"


class SettlementStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PARTIAL = "PARTIAL", "Partially Paid"
    PAID = "PAID", "Paid"
    OVERDUE = "OVERDUE", "Overdue"
    DISPUTED = "DISPUTED", "Disputed"


class DisputeStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"
    ESCALATED = "ESCALATED", "Escalated"


class SyncStatus(models.TextChoices):
    SYNCED = "SYNCED", "Synced"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED", "Duplicate Ignored"
    VALIDATION_FAILED = "VALIDATION_FAILED", "Validation Failed"
    PENDING_PROCESSING = "PENDING_PROCESSING", "Pending Processing"
    ERROR = "ERROR", "Error"


class BlockchainAnchorStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUBMITTED = "SUBMITTED", "Submitted"
    CONFIRMED = "CONFIRMED", "Confirmed"
    FAILED = "FAILED", "Failed"


class NotificationType(models.TextChoices):
    INFO = "INFO", "Info"
    WARNING = "WARNING", "Warning"
    ACTION_REQUIRED = "ACTION_REQUIRED", "Action Required"
    SETTLEMENT = "SETTLEMENT", "Settlement"
    DISPUTE = "DISPUTE", "Dispute"
    SYSTEM = "SYSTEM", "System"


class SeasonStatus(models.TextChoices):
    PLANNING = "PLANNING", "Planning"
    ACTIVE = "ACTIVE", "Active"
    HARVESTING = "HARVESTING", "Harvesting"
    COMPLETED = "COMPLETED", "Completed"


class OTPPurpose(models.TextChoices):
    LOGIN = "LOGIN", "Login"
    REGISTRATION = "REGISTRATION", "Registration"
    PASSWORD_RESET = "PASSWORD_RESET", "Password Reset"


class OTPStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VERIFIED = "VERIFIED", "Verified"
    EXPIRED = "EXPIRED", "Expired"
    MAX_ATTEMPTS = "MAX_ATTEMPTS", "Max Attempts Exceeded"


class WhatsAppDirection(models.TextChoices):
    INBOUND = "INBOUND", "Inbound"
    OUTBOUND = "OUTBOUND", "Outbound"


class WhatsAppDeliveryStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    SENT = "SENT", "Sent"
    DELIVERED = "DELIVERED", "Delivered"
    READ = "READ", "Read"
    FAILED = "FAILED", "Failed"
    UNDELIVERED = "UNDELIVERED", "Undelivered"


class ForecastModelType(models.TextChoices):
    YIELD = "yield", "Yield"
    PRICE = "price", "Price"


class ForecastRunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class ForecastSubjectType(models.TextChoices):
    FARM = "farm", "Farm"
    LOT = "lot", "Lot"
    REGION = "region", "Region"


class AnomalyAlertType(models.TextChoices):
    DOC_DUPLICATE_EXACT = "DOC_DUPLICATE_EXACT", "Document duplicate (exact hash)"
    DOC_DUPLICATE_NEAR = "DOC_DUPLICATE_NEAR", "Document near-duplicate"
    RECEIPT_SALE_MISMATCH = "RECEIPT_SALE_MISMATCH", "Receipt vs sale mismatch"
    EVENT_MISSING = "EVENT_MISSING", "Missing required trace event"
    EVENT_SEQUENCE_BREAK = "EVENT_SEQUENCE_BREAK", "Out-of-order / chain break"
    EVENT_TIME_DELTA_OUTLIER = "EVENT_TIME_DELTA_OUTLIER", "Unrealistic time delta"
    GRADE_JUMP = "GRADE_JUMP", "Grade jump anomaly"
    GRADE_PRICE_MISMATCH = "GRADE_PRICE_MISMATCH", "Grade vs price mismatch"
    YIELD_RESIDUAL_OUTLIER = "YIELD_RESIDUAL_OUTLIER", "Yield vs forecast residual"
    VENDOR_RISK = "VENDOR_RISK", "Vendor risk signal"


class AnomalySeverity(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class AnomalyAlertStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    REVIEWING = "REVIEWING", "Reviewing"
    CLOSED = "CLOSED", "Closed"


class AnomalyEvidenceType(models.TextChoices):
    HASH_MATCH = "hash_match", "Hash match"
    SIMILARITY = "similarity", "Similarity"
    RULE_VIOLATION = "rule_violation", "Rule violation"
    STAT_OUTLIER = "stat_outlier", "Statistical outlier"
    SEQUENCE_BREAK = "sequence_break", "Sequence break"
    VENDOR_RISK = "vendor_risk", "Vendor risk"


class ReviewLabelChoice(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    FALSE_POSITIVE = "false_positive", "False positive"
    NEEDS_INFO = "needs_info", "Needs information"


class DocumentVerificationState(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    HASHED = "HASHED", "Hashed"
    ANCHORED = "ANCHORED", "Anchored"
    VERIFIED = "VERIFIED", "Verified"


class PreferredLanguageCode(models.TextChoices):
    EN = "en", "English"
    SN = "sn", "Shona"
    ND = "nd", "Ndebele"


class LiteracyMode(models.TextChoices):
    NORMAL = "normal", "Normal"
    GUIDED = "guided", "Guided (low-literacy)"


class UXChannel(models.TextChoices):
    FLUTTER = "flutter", "Flutter"
    WHATSAPP = "whatsapp", "WhatsApp"


class DisputeCategory(models.TextChoices):
    GRADING = "grading", "Grading"
    SALE = "sale", "Sale"
    DOCUMENT = "document", "Document"
    SEQUENCE = "sequence", "Trace sequence"


class ModelRunKind(models.TextChoices):
    YIELD = "yield", "Yield forecast"
    PRICE = "price", "Price forecast"
    ANOMALY = "anomaly", "Anomaly"
    DUPLICATE = "duplicate", "Near-duplicate"


class ConversationType(models.TextChoices):
    GENERAL = "GENERAL", "General"
    ONBOARDING = "ONBOARDING", "Onboarding"
    FARM_REGISTRATION = "FARM_REGISTRATION", "Farm Registration"
    SEASON_CREATION = "SEASON_CREATION", "Season Creation"
    LOT_CREATION = "LOT_CREATION", "Lot Creation"
    EVENT_CAPTURE = "EVENT_CAPTURE", "Event Capture"
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD", "Document Upload"
    DISPUTE_CREATION = "DISPUTE_CREATION", "Dispute Creation"
    GRADING = "GRADING", "Grading"
    SALE_RECORDING = "SALE_RECORDING", "Sale Recording"
    SETTLEMENT = "SETTLEMENT", "Settlement"
    DISPUTE_RESPONSE = "DISPUTE_RESPONSE", "Dispute Response"
    AI_QUERY = "AI_QUERY", "AI Query"
