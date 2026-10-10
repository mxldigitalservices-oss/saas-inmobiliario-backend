from app.models.audit_log import AuditLog
from app.models.client import Client
from app.models.contract import Contract
from app.models.expenses import Expense
from app.models.invoice import Invoice
from app.models.media import Media
from app.models.ncf_sequence import NCFSequence
from app.models.payment_gateway import PaymentGateway
from app.models.property import Property
from app.models.reservation import ReservationRequest
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.token import LicenseToken
from app.models.unit import Unit
from app.models.user import User

# Lista única de documentos para init_beanie
ALL_DOCUMENT_MODELS = [
    Tenant,
    User,
    SuperAdmin,
    LicenseToken,
    Property,
    Unit,
    ReservationRequest,
    PaymentGateway,
    Media,
    Client,
    NCFSequence,
    Invoice,
    Expense,
    Contract,
    AuditLog,
]

__all__ = [
    "ALL_DOCUMENT_MODELS",
    "AuditLog",
    "Client",
    "Contract",
    "Expense",
    "Invoice",
    "LicenseToken",
    "Media",
    "NCFSequence",
    "PaymentGateway",
    "Property",
    "ReservationRequest",
    "SuperAdmin",
    "Tenant",
    "Unit",
    "User",
]
