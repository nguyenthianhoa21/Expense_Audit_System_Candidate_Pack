"""Unit test cho R0 - R12: dung du lieu tong hop, khong can API key, khong can DB."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

os.environ["DISABLE_BGE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.extraction import BankBeneficiary, DocType, DocumentExtractionData, LineItem  # noqa: E402
from app.services.audit_engine import AuditEngine  # noqa: E402
from app.services.document_io import read_document_text  # noqa: E402
from app.services.offline_parser import parse_offline_plain_text  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "Sample"


def _mk(dtype, no, total, req=None, *, seller_bank=None, pr_bank=None, buyer="MINH ANH", seller="AN PHU",
         items=None, issue=None, approval="Approved", subtotal=None, vat_rate=10.0, vat=None, refs=None):
    return DocumentExtractionData(
        doc_type=dtype,
        doc_number=no,
        reference_numbers=refs or [],
        issue_date=issue,
        buyer_name=buyer,
        buyer_address=None,
        seller_name=seller,
        seller_address=None,
        requester_name=None,
        department=None,
        payment_purpose=None,
        currency="VND",
        items=items or [],
        subtotal_amount=subtotal if subtotal is not None else total,
        vat_rate=vat_rate,
        vat_amount=vat if vat is not None else ((total - (subtotal if subtotal is not None else total)) if total else None),
        total_amount=total,
        requested_payment_amount=req,
        bank_beneficiary=pr_bank if dtype == DocType.PAYMENT_REQUEST else seller_bank,
        due_date=None,
        approval_status=approval,
    )


def _items():
    # Tra ve list moi moi lan de test nao sua PO khong lan sang Invoice.
    return [LineItem(item_code="A", description="X", quantity=2, unit="c", unit_price=100.0, amount=200.0)]


def good_three():
    bank = BankBeneficiary(account_name="AN PHU", account_number="111", bank_name="B")
    po = _mk(DocType.PO, "PO-1", 220.0, items=_items(), seller_bank=bank, issue=date(2026, 9, 20), subtotal=200.0, vat=20.0, refs=[])
    inv = _mk(DocType.INVOICE, "INV-1", 220.0, items=_items(), seller_bank=bank, issue=date(2026, 9, 28),
               subtotal=200.0, vat=20.0, refs=["PO-1"])
    pr = _mk(DocType.PAYMENT_REQUEST, "PR-1", None, req=220.0, pr_bank=bank, issue=date(2026, 9, 30),
              subtotal=None, vat=None, refs=["PO-1", "INV-1"])
    return {DocType.PO: po, DocType.INVOICE: inv, DocType.PAYMENT_REQUEST: pr}


def test_happy_path_passed():
    docs = good_three()
    verdict, results = AuditEngine().run(docs)
    failed = [r.rule_id for r in results if r.status.value == "FAILED"]
    assert failed == [], failed
    assert verdict.overall_verdict.value == "PASSED"


def test_r2_beneficiary_changed_is_critical():
    docs = good_three()
    docs[DocType.PAYMENT_REQUEST].bank_beneficiary = BankBeneficiary(
        account_name="NGUYEN VAN X", account_number="999", bank_name="B")
    verdict, results = AuditEngine().run(docs)
    r2 = next(r for r in results if r.rule_id == "R2")
    assert r2.status.value == "FAILED" and r2.severity.value == "CRITICAL"
    assert verdict.overall_verdict.value == "REJECTED"


def test_r5_quantity_over_po():
    docs = good_three()
    docs[DocType.INVOICE].items[0].quantity = 5.0
    verdict, results = AuditEngine().run(docs)
    r5 = next(r for r in results if r.rule_id == "R5")
    assert r5.status.value == "FAILED"
    assert verdict.overall_verdict.value == "REJECTED"


def test_r6_price_over_po():
    docs = good_three()
    docs[DocType.INVOICE].items[0].unit_price = 500.0
    verdict, results = AuditEngine().run(docs)
    r6 = next(r for r in results if r.rule_id == "R6")
    assert r6.status.value == "FAILED"


def test_r7_request_mismatch():
    docs = good_three()
    docs[DocType.PAYMENT_REQUEST].requested_payment_amount = 999.0
    verdict, results = AuditEngine().run(docs)
    r7 = next(r for r in results if r.rule_id == "R7")
    assert r7.status.value == "FAILED"


def test_r12_pending_is_medium_warning_only():
    docs = good_three()
    docs[DocType.PAYMENT_REQUEST].approval_status = "Pending"
    verdict, results = AuditEngine().run(docs)
    r12 = next(r for r in results if r.rule_id == "R12")
    assert r12.status.value == "FAILED" and r12.severity.value == "MEDIUM"
    assert verdict.overall_verdict.value == "WARNING"


def test_r0_missing_document():
    docs = good_three()
    docs[DocType.INVOICE] = None
    verdict, results = AuditEngine().run(docs)
    r0 = next(r for r in results if r.rule_id == "R0")
    assert r0.status.value == "FAILED"
    assert verdict.overall_verdict.value == "REJECTED"


def test_r11_bad_chronology():
    docs = good_three()
    docs[DocType.PO].issue_date = date(2026, 10, 5)
    docs[DocType.INVOICE].issue_date = date(2026, 9, 1)
    verdict, results = AuditEngine().run(docs)
    r11 = next(r for r in results if r.rule_id == "R11")
    assert r11.status.value == "FAILED"


def test_offline_parser_on_real_samples():
    for name, dtype in [("Sample_Purchase_Order.pdf", "PO"),
                        ("Sample_Invoice.pdf", "INVOICE"),
                        ("Sample_Payment_Request.pdf", "PAYMENT_REQUEST")]:
        text, meta = read_document_text((SAMPLE / name).read_bytes(), name)
        data = parse_offline_plain_text(text)
        assert data.doc_type.value == dtype, (name, data.doc_type)
        assert data.doc_number, name
    inv = parse_offline_plain_text(
        read_document_text((SAMPLE / "Sample_Invoice.pdf").read_bytes(), "Sample_Invoice.pdf")[0])
    assert inv.vat_rate == 10.0, inv.vat_rate
    assert inv.total_amount == 55220000.0
    assert len(inv.items) == 3


def test_full_batch_on_real_samples_is_rejected():
    docs = {}
    mapping = {"Sample_Purchase_Order.pdf": DocType.PO, "Sample_Invoice.pdf": DocType.INVOICE,
               "Sample_Payment_Request.pdf": DocType.PAYMENT_REQUEST}
    for name, dtype in mapping.items():
        text, _ = read_document_text((SAMPLE / name).read_bytes(), name)
        docs[dtype] = parse_offline_plain_text(text)
    verdict, results = AuditEngine().run(docs)
    assert verdict.overall_verdict.value == "REJECTED"
    failed = {r.rule_id for r in results if r.status.value == "FAILED"}
    assert {"R2", "R3", "R5", "R7", "R12"} <= failed, failed
