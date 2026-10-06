"""Layer 4 - Offline Parser Fallback: pdfplumber/PyMuPDF text + regex, khong dung LLM.

Muc dich: luon tra ve duoc mot bo du lieu cu, du chung ta khong co API key hoac
moi API deu that bai. Chat luong duoc danh dau la "best effort"; Pipeline se ghi
canh bao vao validation_findings o Phase 2 de reviewer biet du lieu nao yeu.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from app.schemas.extraction import BankBeneficiary, DocType, DocumentExtractionData, LineItem

# Document number patterns seen in PO / Invoice / PR documents.
_DOC_NO = r"(?:PO|INV|PR|HÓA|HD)[-_ ]?[\d\-]{3,}"


# ---------------------------------------------------------------- helpers


def _money(raw: str | None) -> float | None:
    """Chuyen '55.220.000' / '3,200,000' / '1.250.000,50' -> float."""
    if raw is None:
        return None
    s = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^\d,\.\-]", "", s)
    if not s or s == "-":
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(",") > s.rfind(".") else s.replace(".", "").replace(",", ".")
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


def _is_number(tok: str) -> bool:
    return bool(re.fullmatch(r"-?[\d][\d\.,]*", tok.strip()))


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", raw)
    if m:
        d, mth, y = m.groups()
        y = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            return date(y, int(mth), int(d))
        except ValueError:
            return None
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", raw)
    if m:
        y, mth, d = m.groups()
        try:
            return date(int(y), int(mth), int(d))
        except ValueError:
            return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


class LineIndex:
    """Tra loi 'gia tri cua nhan X' tren bang text PDF da tach dong."""

    def __init__(self, text: str) -> None:
        self.lines = [ln.rstrip() for ln in text.splitlines()]
        self.text = text

    def value(self, label_patterns: list[str], *, flags: int = re.IGNORECASE) -> str | None:
        for pat in label_patterns:
            rx = re.compile(r"^\s*" + pat + r"\s*[:\-]?\s*(.*)$", flags)
            for i, line in enumerate(self.lines):
                m = rx.match(line)
                if not m:
                    continue
                rest = m.group(1).strip()
                if rest:
                    return rest
                for nxt in self.lines[i + 1 :]:
                    if nxt.strip():
                        return nxt.strip()
        return None

    def find(self, pattern: str, *, flags: int = re.IGNORECASE) -> str | None:
        m = re.search(pattern, self.text, flags)
        return m.group(1).strip() if m and m.lastindex else None


def _first_doc_no(rest: str | None) -> str | None:
    """'Số hóa đơn: INV-2026-0891 Ngày: 28/09/2026' -> 'INV-2026-0891'."""
    if not rest:
        return None
    m = re.search(_DOC_NO, rest, re.IGNORECASE)
    return m.group(0).strip() if m else None


def detect_doc_type(text: str) -> DocType:
    up = text.upper()
    if "PAYMENT REQUEST" in up or "ĐỀ NGHỊ THANH TOÁN" in up:
        return DocType.PAYMENT_REQUEST
    if "PURCHASE ORDER" in up or "ĐƠN ĐẶT HÀNG" in up or "PO NUMBER" in up:
        return DocType.PO
    if "INVOICE" in up or "HÓA ĐƠN" in up or "SỐ HÓA ĐƠN" in up:
        return DocType.INVOICE
    return DocType.PO


def _extract_items(idx: LineIndex) -> list[LineItem]:
    """Doc cac dong hang: <ma> <mo ta...> <sl> <dvt> <don gia> <thanh tien>."""
    items: list[LineItem] = []
    for line in idx.lines:
        toks = line.split()
        if len(toks) < 6:
            continue
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-_\.]{1,15}", toks[0]):
            continue
        if not (_is_number(toks[-4]) and _is_number(toks[-2]) and _is_number(toks[-1])):
            continue
        if _is_number(toks[-3]):
            continue
        items.append(
            LineItem(
                item_code=toks[0],
                description=" ".join(toks[1:-4]) or None,
                quantity=_money(toks[-4]),
                unit=toks[-3],
                unit_price=_money(toks[-2]),
                amount=_money(toks[-1]),
            )
        )
    return items


def parse_offline_plain_text(text: str, doc_type: DocType | None = None) -> DocumentExtractionData:
    idx = LineIndex(text)
    dt = doc_type or detect_doc_type(text)

    doc_number = None
    if dt == DocType.PO:
        doc_number = _first_doc_no(idx.value([r"PO\s+Number", r"PO\s+No\.?"]))
    elif dt == DocType.INVOICE:
        doc_number = _first_doc_no(idx.value([r"Số hóa đơn", r"Invoice\s+No\.?", r"Số\s+HD"]))
    elif dt == DocType.PAYMENT_REQUEST:
        doc_number = _first_doc_no(idx.value([r"Số đề nghị", r"PR\s+No\.?", r"Payment\s+Request\s+No\.?"]))
    if not doc_number:
        doc_number = _first_doc_no(idx.value([r"Số hiệu", r"Document\s+No\.?", r"Số chứng từ"]))
    if not doc_number:
        # Last resort: first doc-no token in the whole text
        m = re.search(_DOC_NO, text, re.IGNORECASE)
        doc_number = m.group(0).strip() if m else None

    all_refs = re.findall(_DOC_NO, text, re.IGNORECASE)
    references = sorted({r.upper() for r in all_refs if r.upper() != (doc_number or "").upper()})

    issue_date = _parse_date(idx.value([r"Ngày đặt hàng", r"Ngày hóa đơn", r"Ngày đề nghị", r"Ngày(?: phát hành)?"]))
    due_date = _parse_date(idx.value([r"Due date", r"Ngày thanh toán mong muốn", r"Hạn thanh toán"]))

    buyer_name = idx.value([r"Bill\s*To\s*/?\s*Bên mua", r"Bên mua", r"Đơn vị đề nghị", r"Buyer"])
    seller_name = idx.value([r"Seller\s*/\s*Bên bán", r"Bên bán", r"Nhà cung cấp", r"Supplier", r"Seller"])

    buyer_address = idx.value([r"Địa chỉ giao hàng", r"Địa chỉ giao", r"Billing address", r"Buyer address"])
    seller_address = idx.value([r"Địa chỉ(?!\s*giao)", r"Seller address", r"Address of seller"])

    currency = idx.value([r"Tiền tệ", r"Currency"])
    currency = (currency or "").upper() if currency else None
    if currency and re.search(r"[A-Z]", currency):
        currency = re.sub(r"[^A-Z]", "", currency)[:3] or None

    subtotal = _money(idx.value([r"Subtotal", r"Sub\s*total", r"Cộng tiền hàng", r"Tổng tiền hàng(?!\s*VAT)"]))
    vat_rate = None
    _vat_label = idx.value([r"VAT\s*\(\s*\d+\s*%\s*\)", r"VAT\s*\d+\s*%", r"Thuế suất VAT"])
    if _vat_label:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", _vat_label)
        if m:
            try:
                vat_rate = float(m.group(1))
            except ValueError:
                pass
    if vat_rate is None:
        m = re.search(r"VAT\s*\(?\s*(\d+(?:\.\d+)?)\s*%", idx.text)
        if m:
            try:
                vat_rate = float(m.group(1))
            except ValueError:
                pass
    vat_amount = _money(idx.value([r"VAT(?:\s*\(\s*\d+\s*%\s*\)|\s*\d+\s*%)?"]))
    total_amount = _money(idx.value([r"Total\s*Due(?:\s*\(VND\))?", r"Tổng cộng", r"Total(?: cộng)?(?!\s*Due)"]))
    requested = _money(idx.value([r"Số tiền đề nghị thanh toán", r"Số tiền đề nghị"]))
    if requested is None:
        requested = _money(idx.value([r"Giá trị hóa đơn"]))

    account_name = idx.value([r"Tên tài khoản", r"Account name", r"Chủ tài khoản", r"Beneficiary name"])
    account_number = idx.value([r"Số tài khoản", r"Account\s*(?:number|no)", r"Beneficiary account"])
    account_number = "".join(ch for ch in (account_number or "") if ch.isdigit()) or None
    bank_name = idx.value([r"Ngân hàng", r"Bank(?:\s*name)?"])

    requester = idx.value([r"Người đề nghị", r"Requester", r"Prepared by"])
    department = idx.value([r"Phòng ban", r"Department"])
    if requester and " - " in requester and not department:
        requester, _, dept = requester.partition(" - ")
        if len(dept.strip()) <= 12:
            department = dept.strip()
    purpose = idx.value([r"Nội dung thanh toán", r"Payment purpose", r"Mục đích"])

    approval = idx.find(r"(?:Kế toán trưởng|Chief Accountant)[^\n]*?\b(Pending|Approved|Rejected)\b")
    if not approval:
        approval = idx.find(r"Trạng thái\s*[:\-]?\s*([A-Za-z]+)")

    return DocumentExtractionData(
        doc_type=dt,
        doc_number=doc_number,
        reference_numbers=references,
        issue_date=issue_date,
        buyer_name=buyer_name,
        buyer_address=buyer_address,
        seller_name=seller_name,
        seller_address=seller_address,
        requester_name=requester,
        department=department,
        payment_purpose=purpose,
        currency=currency,
        items=_extract_items(idx),
        subtotal_amount=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_amount=total_amount,
        requested_payment_amount=requested,
        bank_beneficiary=(
            BankBeneficiary(account_name=account_name, account_number=account_number, bank_name=bank_name)
            if (account_name or account_number)
            else None
        ),
        due_date=due_date,
        approval_status=approval,
    )
