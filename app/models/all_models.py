from app.models.cliente import Cliente
from app.models.propiedad import Propiedad
from app.models.unidad import Unidad
from app.models.factura import Factura
from app.models.inquilino import Inquilino
from app.models.super_admin import SuperAdmin
from app.models.audit_log import AuditLog
from app.models.gastos import Gastos
from app.models.media import Media
from app.models.ncf_sequence import NcfSequence
from app.models.payment_gateway import PaymentGateway
from app.models.reserva import Reserva

ALL_DOCUMENT_MODELS = [
    Cliente,
    Propiedad,
    Unidad,
    Factura,
    Inquilino,
    SuperAdmin,
    AuditLog,
    Gastos,
    Media,
    NcfSequence,
    PaymentGateway,
    Reserva,
]
