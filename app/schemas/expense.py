from datetime import date, datetime
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import DGIIPaymentForm, ExpenseStatus, ExpenseType
from app.models.expenses import ExpenseAmounts, Supplier
from app.schemas.common import PERIOD_REGEX, TimestampedOut


class ExpenseCreate(BaseModel):
    supplier: Supplier
    expense_type: ExpenseType = ExpenseType.TRABAJOS_SUMINISTROS_SERVICIOS
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=80)
    ncf: Optional[str] = Field(None, max_length=13)
    ncf_modified: Optional[str] = Field(None, max_length=13)
    receipt_date: Optional[datetime] = None
    payment_date: Optional[datetime] = None
    payment_form: DGIIPaymentForm = DGIIPaymentForm.EFECTIVO
    amounts: ExpenseAmounts = Field(default_factory=ExpenseAmounts)
    attachment_media_id: Optional[PydanticObjectId] = None

    @field_validator("ncf", "ncf_modified")
    @classmethod
    def _ncf(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else v

    @model_validator(mode="after")
    def _fill_total(self):
        a = self.amounts
        if a.total_amount == 0:
            a.total_amount = a.services_amount + a.goods_amount
        return self


class ExpenseUpdate(BaseModel):
    supplier: Optional[Supplier] = None
    expense_type: Optional[ExpenseType] = None
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=80)
    ncf: Optional[str] = Field(None, max_length=13)
    ncf_modified: Optional[str] = Field(None, max_length=13)
    receipt_date: Optional[datetime] = None
    payment_date: Optional[datetime] = None
    payment_form: Optional[DGIIPaymentForm] = None
    amounts: Optional[ExpenseAmounts] = None
    attachment_media_id: Optional[PydanticObjectId] = None

    @field_validator("ncf", "ncf_modified")
    @classmethod
    def _ncf(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else v


class ExpenseVoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ExpenseOut(TimestampedOut):
    tenant_id: PydanticObjectId
    supplier: Supplier
    expense_type: ExpenseType
    description: Optional[str] = None
    category: Optional[str] = None
    ncf: Optional[str] = None
    ncf_modified: Optional[str] = None
    receipt_date: datetime
    payment_date: Optional[datetime] = None
    payment_form: DGIIPaymentForm
    amounts: ExpenseAmounts
    status: ExpenseStatus
    attachment_media_id: Optional[PydanticObjectId] = None
    created_by: Optional[PydanticObjectId] = None
    period: Optional[str] = None


class ExpenseFilter(BaseModel):
    status: Optional[ExpenseStatus] = None
    expense_type: Optional[ExpenseType] = None
    category: Optional[str] = None
    supplier_tax_id: Optional[str] = None
    period: Optional[str] = Field(None, pattern=PERIOD_REGEX)
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @model_validator(mode="after")
    def _range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from no puede ser posterior a date_to")
        return self
