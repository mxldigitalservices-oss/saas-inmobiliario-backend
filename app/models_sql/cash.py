"""Caja y transacciones financieras (persistencia estricta en PostgreSQL).

El tenant_id y user_id referencian documentos de MongoDB (ObjectId como string de 24 chars).
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.postgres_db import Base

MONEY = Numeric(14, 2)


class CashRegisterStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class TransactionType(str, enum.Enum):
    INCOME = "income"        # ingreso (pago de factura, depósito...)
    EXPENSE = "expense"      # egreso (gasto, pago a proveedor...)
    ADJUSTMENT = "adjustment"  # ajuste de caja
    REFUND = "refund"        # devolución


class CashRegister(Base):
    """Caja / turno de caja de un tenant."""

    __tablename__ = "cash_registers"
    __table_args__ = (
        Index("ix_cash_registers_tenant_status", "tenant_id", "status"),
        CheckConstraint("opening_balance >= 0", name="ck_cash_registers_opening_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="DOP")
    status: Mapped[CashRegisterStatus] = mapped_column(
        Enum(CashRegisterStatus, name="cash_register_status"),
        default=CashRegisterStatus.OPEN,
    )
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    closing_balance: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    opened_by: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    transactions: Mapped[List["CashTransaction"]] = relationship(
        back_populates="register", cascade="all, delete-orphan"
    )


class CashTransaction(Base):
    """Movimiento financiero inmutable (no se edita; se corrige con un ajuste/reverso)."""

    __tablename__ = "cash_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_transactions_amount_positive"),
        # Idempotencia: evita registrar dos veces la misma operación (reintentos, webhooks)
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_cash_transactions_idempotency"
        ),
        Index("ix_cash_transactions_tenant_created", "tenant_id", "created_at"),
        Index("ix_cash_transactions_reference", "tenant_id", "reference_type", "reference_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(24), index=True)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cash_registers.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="cash_transaction_type")
    )
    amount: Mapped[Decimal] = mapped_column(MONEY)  # siempre positivo; el tipo define el signo
    currency: Mapped[str] = mapped_column(String(3), default="DOP")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Enlace a documentos de Mongo (p. ej. reference_type="invoice", reference_id=<ObjectId>)
    reference_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    register: Mapped[CashRegister] = relationship(back_populates="transactions")
