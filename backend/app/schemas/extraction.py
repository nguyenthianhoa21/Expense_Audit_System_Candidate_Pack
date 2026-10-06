from __future__ import annotations
from datetime import date
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class DocType(str, Enum):
    PO = "PO"
    INVOICE = "INVOICE"
    PAYMENT_REQUEST = "PAYMENT_REQUEST"

class LineItem(BaseModel):
    item_code: str | None = Field(default=None)
    description: str | None = Field(default=None)
    quantity: float | None = Field(default=None)
    unit: str | None = Field(default=None)
    unit_price: float | None = Field(default=None)
    amount: float | None = Field(default=None)

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def _to_float(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        s = str(v).strip()
        if not s:
            return None
        s = s.replace("\u00a0", " ").replace(" ", "")
        # "55.220.000" (VN) hoac "3,200,000" (US) -> 55220000 / 3200000
        if "." in s and "," in s:
            s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", "")
        else:
            head, sep, tail = s.rpartition(".")
            if sep and head.isdigit() and tail.isdigit() and len(tail) != 3:
                s = head + "." + tail
            else:
                s = s.replace(".", "")
        try:
            return float(s)
        except ValueError:
            return None

class BankBeneficiary(BaseModel):
    account_name: str | None = Field(default=None)
    account_number: str | None = Field(default=None)
    bank_name: str | None = Field(default=None)

    @field_validator("account_number", mode="before")
    @classmethod
    def _digits_only(cls, v):
        if v is None:
            return None
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return digits or None

class DocumentExtractionData(BaseModel):
    """Schema chuan 18 truong (ma tran trich xuat cua de bai)."""

    doc_type: DocType
    doc_number: str | None = Field(default=None)
    reference_numbers: list[str] = Field(default_factory=list)
    issue_date: date | None = Field(default=None)
    buyer_name: str | None = Field(default=None)
    buyer_address: str | None = Field(default=None)
    seller_name: str | None = Field(default=None)
    seller_address: str | None = Field(default=None)
    requester_name: str | None = Field(default=None)
    department: str | None = Field(default=None)
    payment_purpose: str | None = Field(default=None)
    currency: str | None = Field(default=None)
    items: list[LineItem] = Field(default_factory=list)
    subtotal_amount: float | None = Field(default=None)
    vat_rate: float | None = Field(default=None)
    vat_amount: float | None = Field(default=None)
    total_amount: float | None = Field(default=None)
    requested_payment_amount: float | None = Field(default=None)
    bank_beneficiary: BankBeneficiary | None = Field(default=None)

    # --- Truong bo sung (ngoai ma tran 18 truong) ---
    # Hai truong nay khong co trong ma tran 18 truong cua de bai nhanh du R11/R12
    # (deadline + trang thai phe duyet) lai can de kiem tra. Thay vi ep LLM tu
    # suy dien, ta tach rieng va gan gia tri null de co the dua vao ma tran 18 truong
    # khi can.
    due_date: date | None = Field(default=None)
    approval_status: str | None = Field(default=None)

    @field_validator(
        "subtotal_amount",
        "vat_rate",
        "vat_amount",
        "total_amount",
        "requested_payment_amount",
        mode="before",
    )
    @classmethod
    def _num(cls, v):
        return LineItem._to_float(v)

    @field_validator("issue_date", mode="before")
    @classmethod
    def _date(cls, v):
        if v is None or isinstance(v, date):
            return v
        s = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
            try:
                from datetime import datetime
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @field_validator("reference_numbers", mode="before")
    @classmethod
    def _refs(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v):
        if v is None:
            return None
        s = str(v).strip().upper()
        return {"VNĐ": "VND", "VN": "VND", "D": "VND"}.get(s, s) or None
