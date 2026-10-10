from enum import Enum


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class PlanType(str, Enum):
    TRIAL_30D = "trial_30d"
    ANNUAL = "annual"
    CUSTOM = "custom"


class LicenseStatus(str, Enum):
    UNUSED = "unused"
    REDEEMED = "redeemed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class PropertyKind(str, Enum):
    SINGLE = "single"
    PROJECT = "project"


class OperationType(str, Enum):
    SALE = "sale"
    RENT = "rent"
    BOTH = "both"


class PropertyType(str, Enum):
    HOUSE = "house"
    APARTMENT = "apartment"
    LAND = "land"
    COMMERCIAL = "commercial"
    VILLA = "villa"
    OTHER = "other"


class PublishStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Lifecycle(str, Enum):
    EN_PLANO = "en_plano"
    CONSTRUCCION = "construccion"
    LISTO = "listo"


class SingleAvailability(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    RENTED = "rented"


class UnitAvailability(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ReservationSource(str, Enum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    MANUAL = "manual"


class PaymentProvider(str, Enum):
    STRIPE = "stripe"
    AZUL = "azul"
    CARDNET = "cardnet"


class GatewayEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class MediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class MediaStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class StorageProvider(str, Enum):
    S3 = "s3"
    R2 = "r2"
    RAILWAY_VOLUME = "railway_volume"


class MediaOwnerType(str, Enum):
    PROPERTY = "property"
    UNIT = "unit"
    TENANT = "tenant"
    USER = "user"


class ClientType(str, Enum):
    PERSON = "person"
    COMPANY = "company"


class TaxIdType(str, Enum):
    RNC = "rnc"
    CEDULA = "cedula"
    PASSPORT = "passport"


class ClientStage(str, Enum):
    LEAD = "lead"
    PROSPECT = "prospect"
    CLIENT = "client"


class NCFStatus(str, Enum):
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    DISABLED = "disabled"


class InvoiceStatus(str, Enum):
    ISSUED = "issued"
    PAID = "paid"
    VOIDED = "voided"


class PaymentMethod(str, Enum):
    CASH = "cash"
    TRANSFER = "transfer"
    CARD = "card"
    CHECK = "check"
    CREDIT = "credit"
    BARTER = "barter"
    MIXED = "mixed"


class IncomeType(str, Enum):
    """Tipo de ingreso del Reporte 607 (DGII)."""

    OPERACIONES = "01"
    FINANCIEROS = "02"
    EXTRAORDINARIOS = "03"
    ARRENDAMIENTOS = "04"
    VENTA_ACTIVO_DEPRECIABLE = "05"
    OTROS = "06"


class ExpenseType(str, Enum):
    """Tipo de bienes y servicios comprados del Reporte 606 (DGII)."""

    GASTOS_PERSONAL = "01"
    TRABAJOS_SUMINISTROS_SERVICIOS = "02"
    ARRENDAMIENTOS = "03"
    ACTIVOS_FIJOS = "04"
    REPRESENTACION = "05"
    OTRAS_DEDUCCIONES = "06"
    FINANCIEROS = "07"
    EXTRAORDINARIOS = "08"
    COSTO_VENTA = "09"
    ADQUISICION_ACTIVOS = "10"
    SEGUROS = "11"


class DGIIPaymentForm(str, Enum):
    """Forma de pago del Reporte 606 (DGII)."""

    EFECTIVO = "01"
    CHEQUE_TRANSFERENCIA_DEPOSITO = "02"
    TARJETA = "03"
    CREDITO = "04"
    PERMUTA = "05"
    NOTA_CREDITO = "06"
    MIXTO = "07"


class ExpenseStatus(str, Enum):
    RECORDED = "recorded"
    VOIDED = "voided"


class ContractType(str, Enum):
    SALE = "sale"
    RENT = "rent"
    RESERVATION = "reservation"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    CANCELLED = "cancelled"


class AuditActorType(str, Enum):
    USER = "user"
    SUPER_ADMIN = "super_admin"
    SYSTEM = "system"
