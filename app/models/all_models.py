from app.models.client import Client
from app.models.property import Property
from app.models.unit import Unit
from app.models.invoice import Invoice
from app.models.tenant import Tenant
from app.models.super_admin import SuperAdmin
from app.models.audit_log import AuditLog
from app.models.expenses import Expense
from app.models.media import Media
from app.models.ncf_sequence import NcfSequence
from app.models.payment_gateway import PaymentGateway
from app.models.reservation import Reservation

ALL_DOCUMENT_MODELS = [
    Client,
    Property,
    Unit,
    Invoice,
    Tenant,
    SuperAdmin,
    AuditLog,
    Expense,
    Media,
    NcfSequence,
    PaymentGateway,
    Reservation,
]
