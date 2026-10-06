"""Deterministic Audit Engine: chay 13 quy tac R0 - R12 bang Python thuan.

Nguyen tac: khong co LLM trong file nay. Moi phan toan, moi so sanh deu la
code thuan tien dinh -> ket qua lap lai duoc va co the giai thich cho reviewer.
LLM chi lo phan doc chứng từ (Extraction Engine); phan kiem toan thuoc ve file nay.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from app.schemas.extraction import BankBeneficiary, DocType, DocumentExtractionData, LineItem
from app.schemas.validation import (
    SEVERITY_ORDER,
    RuleResult,
    RuleStatus,
    Severity,
    Verdict,
    VerdictResult,
)
from app.services.bge_matcher import BGEMatcher

logger = logging.getLogger(__name__)

# Dung sai tien te: dung sai <= 1 VND theo de bai.
TOLERANCE_VND = 1.0
# Voi so tien lon (tiy dong VND), 1 VND la sai so rat nho; dung 1 VND nhu de bai yeu cau.
AMOUNT_TOLERANCE = TOLERANCE_VND

RULE_NAMES: dict[str, str] = {
    "R0": "RULE_MISSING_DOCUMENT",
    "R1": "RULE_PO_INVOICE_REF_MATCH",
    "R2": "RULE_BENEFICIARY_FRAUD_CHECK",
    "R3": "RULE_LINE_ITEM_MATH_INTERNAL",
    "R4": "RULE_SUBTOTAL_VAT_TOTAL_INTERNAL",
    "R5": "RULE_ITEM_QUANTITY_MATCH",
    "R6": "RULE_ITEM_PRICE_MATCH",
    "R7": "RULE_TOTAL_AMOUNT_MATCH",
    "R8": "RULE_SELLER_NAME_SIMILARITY",
    "R9": "RULE_BUYER_NAME_SIMILARITY",
    "R10": "RULE_ADDRESS_CONSISTENCY",
    "R11": "RULE_DATE_CHRONOLOGY",
    "R12": "RULE_APPROVAL_STATUS",
}

# Muc do mac dinh cua tung quy tac (khi that bai).
RULE_SEVERITY: dict[str, Severity] = {
    "R0": Severity.HIGH,
    "R1": Severity.HIGH,
    "R2": Severity.CRITICAL,
    "R3": Severity.HIGH,
    "R4": Severity.HIGH,
    "R5": Severity.HIGH,
    "R6": Severity.HIGH,
    "R7": Severity.HIGH,
    "R8": Severity.MEDIUM,
    "R9": Severity.MEDIUM,
    "R10": Severity.LOW,
    "R11": Severity.MEDIUM,
    "R12": Severity.MEDIUM,
}

REQUIRED_DOC_TYPES = (DocType.PO, DocType.INVOICE, DocType.PAYMENT_REQUEST)


def _diff(a: float, b: float, tol: float = AMOUNT_TOLERANCE) -> float:
    return abs(a - b)


def _within(a: float, b: float, tol: float = AMOUNT_TOLERANCE) -> bool:
    return _diff(a, b, tol) <= tol


class AuditEngine:
    """Chạy toàn bộ R0 - R12 trên 3 chứng từ da trich xuat."""

    def __init__(self, tolerance: float = AMOUNT_TOLERANCE) -> None:
        self.tolerance = tolerance
        self._matcher = BGEMatcher()

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _result(rule_id: str, status: RuleStatus, message: str, *, details: dict | None = None) -> RuleResult:
        return RuleResult(
            rule_id=rule_id,
            rule_name=RULE_NAMES[rule_id],
            status=status,
            severity=RULE_SEVERITY[rule_id] if status == RuleStatus.FAILED else Severity.INFO,
            message=message,
            details=details or {},
        )

    def _needs(self, *docs: DocumentExtractionData | None) -> list[str]:
        return [d.doc_type.value for d in docs if d is None]

    # --------------------------------------------------------------- R0

    def rule_missing_document(self, docs: dict[DocType, DocumentExtractionData | None]) -> RuleResult:
        missing = [t.value for t in REQUIRED_DOC_TYPES if docs.get(t) is None]
        if missing:
            return self._result(
                "R0",
                RuleStatus.FAILED,
                f"Thiếu chứng từ: {', '.join(missing)}. Hồ sơ thanh toán cần đủ 3/3 chứng từ.",
                details={"missing": missing},
            )
        return self._result("R0", RuleStatus.PASSED, "Đã có đủ 3 chứng từ PO, Invoice, Payment Request.")

    # --------------------------------------------------------------- R1

    def rule_po_invoice_ref_match(
        self, po: DocumentExtractionData | None, inv: DocumentExtractionData | None, pr: DocumentExtractionData | None
    ) -> RuleResult:
        if po is None:
            return self._result("R1", RuleStatus.SKIPPED, "Thiếu PO nen khong kiem tra cross-reference.")
        if inv is None and pr is None:
            return self._result("R1", RuleStatus.SKIPPED, "Thiếu Invoice và PR.")

        po_no = (po.doc_number or "").strip().upper()
        if not po_no:
            return self._result("R1", RuleStatus.SKIPPED, "PO không có số hiệu để so sánh.")

        problems: list[str] = []
        checked: list[str] = []
        for label, doc in (("Invoice", inv), ("Payment Request", pr)):
            if doc is None:
                continue
            refs = [r.strip().upper() for r in (doc.reference_numbers or [])]
            checked.append(label)
            if not refs:
                problems.append(f"{label} không có số tham chiếu nào")
            elif po_no not in refs:
                problems.append(f"{label} không tham chiếu PO {po_no} (refs={refs})")

        if problems:
            return self._result("R1", RuleStatus.FAILED, "; ".join(problems), details={"po_number": po_no})
        return self._result("R1", RuleStatus.PASSED, f"Cả {len(checked)} chứng từ đều tham chiếu {po_no}.",
                           details={"po_number": po_no})

    # --------------------------------------------------------------- R2

    @staticmethod
    def _acct(bank: BankBeneficiary | None) -> str | None:
        if bank is None or not bank.account_number:
            return None
        return "".join(ch for ch in bank.account_number if ch.isdigit()) or None

    def rule_beneficiary_fraud_check(
        self, po: DocumentExtractionData | None, inv: DocumentExtractionData | None, pr: DocumentExtractionData | None
    ) -> RuleResult:
        if pr is None:
            return self._result("R2", RuleStatus.SKIPPED, "Thiếu Payment Request.")
        pr_bank = pr.bank_beneficiary
        if pr_bank is None or not pr_bank.account_number:
            return self._result("R2", RuleStatus.INSUFFICIENT_DATA, "PR không có thông tin tài khoản thụ hưởng.")

        pr_acct = self._acct(pr_bank)
        # Tài khoản pháp nhân bên bán trên Invoice/PO (ưu tiên Invoice rồi PO).
        ref_bank = None
        ref_src = None
        for label, doc in (("Invoice", inv), ("PO", po)):
            if doc is not None and doc.bank_beneficiary and doc.bank_beneficiary.account_number:
                ref_bank = doc.bank_beneficiary
                ref_src = label
                break

        if ref_bank is None or not ref_bank.account_number:
            return self._result(
                "R2",
                RuleStatus.INSUFFICIENT_DATA,
                "Không tìm thấy tài khoản pháp nhân trên Invoice/PO để so sánh.",
                details={"pr_account": pr_acct},
            )

        ref_acct = self._acct(ref_bank)
        if pr_acct != ref_acct:
            return self._result(
                "R2",
                RuleStatus.FAILED,
                f"Tài khoản thụ hưởng trên PR không khớp tài khoản bên bán trên {ref_src}. "
                "Dấu hiệu chuyển tiền sang tài khoản khác (nguy cơ gian lận thanh toán).",
                details={
                    "expected_value": ref_acct,
                    "actual_value": pr_acct,
                    "expected_name": ref_bank.account_name,
                    "actual_name": pr_bank.account_name,
                    "source": ref_src,
                },
            )

        # Khớp số TK nhưng tên chủ TK khác nhau -> cảnh báo thêm (vẫn là CRITICAL).
        name_mismatch = False
        if pr_bank.account_name and ref_bank.account_name:
            match, _, diff = self._matcher.compare_entities(ref_bank.account_name, pr_bank.account_name)
            name_mismatch = not match
        if name_mismatch:
            return self._result(
                "R2",
                RuleStatus.FAILED,
                "Số tài khoản khớp nhưng tên chủ tài khoản thụ hưởng không phải pháp nhân bên bán.",
                details={
                    "expected_value": ref_bank.account_name,
                    "actual_value": pr_bank.account_name,
                    "source": ref_src,
                },
            )

        return self._result("R2", RuleStatus.PASSED, f"Tài khoản thụ hưởng khớp {ref_src}.",
                           details={"account": pr_acct})

    # ----------------------------------------------------------- R3 / R4

    def _check_line_items(self, rule_id: str, doc: DocumentExtractionData | None) -> RuleResult:
        if doc is None:
            return self._result(rule_id, RuleStatus.SKIPPED, f"Thiếu {doc.doc_type.value if doc else 'chứng từ'}.")
        bad: list[dict] = []
        for it in doc.items:
            if it.quantity is None or it.unit_price is None or it.amount is None:
                continue
            expected = it.quantity * it.unit_price
            if not _within(expected, it.amount, self.tolerance):
                bad.append(
                    {
                        "item_code": it.item_code,
                        "expected": expected,
                        "actual": it.amount,
                        "diff": _diff(expected, it.amount),
                    }
                )
        if bad:
            parts = ", ".join(
                f"{b['item_code'] or '?'} (qty*price={b['expected']:.0f} != amount={b['actual']:.0f})" for b in bad
            )
            return self._result(rule_id, RuleStatus.FAILED, f"Sai số học nội bộ dòng hàng: {parts}", details={"items": bad})
        return self._result(rule_id, RuleStatus.PASSED, "Dòng hàng: quantity × đơn giá = thành tiền.")

    def rule_line_item_math(self, po: DocumentExtractionData | None, inv: DocumentExtractionData | None,
                            pr: DocumentExtractionData | None) -> RuleResult:
        parts: list[RuleResult] = []
        for doc in (po, inv, pr):
            parts.append(self._check_line_items("R3", doc))
        failed = [p for p in parts if p.status == RuleStatus.FAILED]
        if failed:
            merged: list[dict] = []
            for p in failed:
                merged.extend(p.details.get("items", []))
            return self._result("R3", RuleStatus.FAILED,
                                f"{len(failed)} chứng từ có dòng hàng sai số học.", details={"items": merged})
        skipped = all(p.status == RuleStatus.SKIPPED for p in parts)
        status = RuleStatus.SKIPPED if skipped else RuleStatus.PASSED
        return self._result("R3", status, "Không có dòng hàng sai số học nội bộ.")

    def rule_subtotal_vat_total(self, po: DocumentExtractionData | None, inv: DocumentExtractionData | None,
                                pr: DocumentExtractionData | None) -> RuleResult:
        problems: list[str] = []
        details: list[dict] = []
        checked = 0

        for doc in (po, inv):
            if doc is None:
                continue
            # (a) subtotal + vat == total
            if doc.subtotal_amount is not None and doc.vat_amount is not None and doc.total_amount is not None:
                checked += 1
                expected_total = doc.subtotal_amount + doc.vat_amount
                if not _within(expected_total, doc.total_amount, self.tolerance):
                    problems.append(
                        f"{doc.doc_type.value}: subtotal + VAT ({doc.subtotal_amount:.0f} + {doc.vat_amount:.0f}"
                        f" = {expected_total:.0f}) != total ({doc.total_amount:.0f})"
                    )
                    details.append(
                        {
                            "doc_type": doc.doc_type.value,
                            "expected": expected_total,
                            "actual": doc.total_amount,
                        }
                    )
            # (b) sum(items.amount) == subtotal
            if doc.subtotal_amount is not None and doc.items:
                checked += 1
                items_sum = sum(it.amount for it in doc.items if it.amount is not None)
                if not _within(items_sum, doc.subtotal_amount, self.tolerance):
                    problems.append(
                        f"{doc.doc_type.value}: tong dong hang ({items_sum:.0f}) != subtotal ({doc.subtotal_amount:.0f})"
                    )
                    details.append(
                        {
                            "doc_type": doc.doc_type.value,
                            "expected": doc.subtotal_amount,
                            "actual": items_sum,
                        }
                    )

        if problems:
            return self._result("R4", RuleStatus.FAILED, "; ".join(problems), details={"checks": details})
        if checked == 0:
            return self._result("R4", RuleStatus.INSUFFICIENT_DATA, "Không đủ subtotal/VAT/tổng để kiểm tra.")
        return self._result("R4", RuleStatus.PASSED, "subtotal + VAT = tổng và tổng các dòng = subtotal.")

    # ------------------------------------------------------------ R5 / R6

    @staticmethod
    def _item_map(doc: DocumentExtractionData | None) -> dict[str, LineItem]:
        out: dict[str, LineItem] = {}
        if doc is None:
            return out
        for it in doc.items:
            key = (it.item_code or (it.description or "")).strip().upper()
            if key:
                out[key] = it
        return out

    def rule_item_quantity_match(self, po: DocumentExtractionData | None,
                                 inv: DocumentExtractionData | None) -> RuleResult:
        if po is None or inv is None:
            return self._result("R5", RuleStatus.SKIPPED, "Cần đủ PO và Invoice.")
        po_items, inv_items = self._item_map(po), self._item_map(inv)
        if not po_items or not inv_items:
            return self._result("R5", RuleStatus.INSUFFICIENT_DATA, "Thiếu dữ liệu dòng hàng để so sánh số lượng.")

        over: list[dict] = []
        missing: list[str] = []
        for code, po_it in po_items.items():
            inv_it = inv_items.get(code)
            if inv_it is None:
                missing.append(code)
                continue
            if po_it.quantity is None or inv_it.quantity is None:
                continue
            if inv_it.quantity > po_it.quantity:
                over.append({"item_code": code, "po_qty": po_it.quantity, "invoice_qty": inv_it.quantity})

        msgs: list[str] = []
        details: dict = {"over": over, "missing_on_invoice": missing}
        if over:
            msgs.append(
                "Số lượng trên Invoice vượt PO: "
                + ", ".join(f"{o['item_code']} (PO={o['po_qty']:.0f}, Inv={o['invoice_qty']:.0f})" for o in over)
            )
        if missing:
            msgs.append("Hàng hoá có trên PO nhưng không có trên Invoice: " + ", ".join(missing))
        if msgs:
            return self._result("R5", RuleStatus.FAILED, "; ".join(msgs), details=details)
        return self._result("R5", RuleStatus.PASSED, "Số lượng trên Invoice không vượt PO.")

    def rule_item_price_match(self, po: DocumentExtractionData | None,
                              inv: DocumentExtractionData | None) -> RuleResult:
        if po is None or inv is None:
            return self._result("R6", RuleStatus.SKIPPED, "Cần đủ PO và Invoice.")
        po_items, inv_items = self._item_map(po), self._item_map(inv)
        if not po_items or not inv_items:
            return self._result("R6", RuleStatus.INSUFFICIENT_DATA, "Thiếu dữ liệu dòng hàng để so sánh đơn giá.")

        over: list[dict] = []
        for code, po_it in po_items.items():
            inv_it = inv_items.get(code)
            if inv_it is None:
                continue
            if po_it.unit_price is None or inv_it.unit_price is None:
                continue
            if inv_it.unit_price > po_it.unit_price:
                over.append({"item_code": code, "po_price": po_it.unit_price, "invoice_price": inv_it.unit_price})

        if over:
            msg = "Don gia tren Invoice vượt PO: " + ", ".join(
                f"{o['item_code']} (PO={o['po_price']:.0f}, Inv={o['invoice_price']:.0f})" for o in over
            )
            return self._result("R6", RuleStatus.FAILED, msg, details={"over": over})
        return self._result("R6", RuleStatus.PASSED, "Đơn giá trên Invoice không vượt PO.")

    # --------------------------------------------------------------- R7

    def rule_total_amount_match(self, po: DocumentExtractionData | None,
                                inv: DocumentExtractionData | None,
                                pr: DocumentExtractionData | None) -> RuleResult:
        problems: list[str] = []
        details: list[dict] = []
        checked = 0

        if po is not None and inv is not None and po.total_amount is not None and inv.total_amount is not None:
            checked += 1
            if inv.total_amount > po.total_amount:
                problems.append(
                    f"Tổng Invoice ({inv.total_amount:.0f}) vượt tổng PO ({po.total_amount:.0f})"
                )
                details.append({"check": "invoice_vs_po_total", "expected": po.total_amount, "actual": inv.total_amount})

        if inv is not None and pr is not None and inv.total_amount is not None and pr.requested_payment_amount is not None:
            checked += 1
            if not _within(pr.requested_payment_amount, inv.total_amount, self.tolerance):
                problems.append(
                    f"Số tiền đề nghị trên PR ({pr.requested_payment_amount:.0f}) không trùng Invoice ({inv.total_amount:.0f})"
                )
                details.append(
                    {"check": "pr_request_vs_invoice_total", "expected": inv.total_amount, "actual": pr.requested_payment_amount}
                )

        if problems:
            return self._result("R7", RuleStatus.FAILED, "; ".join(problems), details={"checks": details})
        if checked == 0:
            return self._result("R7", RuleStatus.INSUFFICIENT_DATA, "Không đủ tổng tiền để so sánh.")
        return self._result("R7", RuleStatus.PASSED, "Tổng tiền khớp giữa PO, Invoice và PR.")

    # ---------------------------------------------------------- R8 / R9 / R10

    def _compare_names(self, rule_id: str, label: str, values: dict[str, str | None]) -> RuleResult:
        present = {k: v for k, v in values.items() if v}
        if len(present) < 2:
            return self._result(rule_id, RuleStatus.SKIPPED, f"Thiếu {label} trên ít nhất 2 chứng từ để so sánh.")

        base_label, base_value = next(iter(present.items()))
        mismatches: list[dict] = []
        for other_label, other_value in list(present.items())[1:]:
            match, similarity, diff_tokens = self._matcher.compare_entities(base_value, other_value)
            if not match:
                mismatches.append(
                    {
                        "base": base_label,
                        "base_value": base_value,
                        "other": other_label,
                        "other_value": other_value,
                        "similarity": similarity,
                        "diff_tokens": diff_tokens,
                    }
                )
        if mismatches:
            parts = ", ".join(
                f"{m['base']}='{m['base_value']}' vs {m['other']}='{m['other_value']}'"
                f" (sim={m['similarity']:.3f}, tokens khac={m['diff_tokens']})"
                for m in mismatches
            )
            return self._result(rule_id, RuleStatus.FAILED, f"{label} không nhất quán: {parts}",
                                details={"mismatches": mismatches})
        return self._result(rule_id, RuleStatus.PASSED, f"{label} nhất quán trên các chứng từ.")

    def rule_seller_name_similarity(self, po: DocumentExtractionData | None,
                                    inv: DocumentExtractionData | None,
                                    pr: DocumentExtractionData | None) -> RuleResult:
        return self._compare_names(
            "R8",
            "Tên bên bán",
            {
                "PO": po.seller_name if po else None,
                "Invoice": inv.seller_name if inv else None,
                "PR": pr.seller_name if pr else None,
            },
        )

    def rule_buyer_name_similarity(self, po: DocumentExtractionData | None,
                                   inv: DocumentExtractionData | None,
                                   pr: DocumentExtractionData | None) -> RuleResult:
        return self._compare_names(
            "R9",
            "Tên bên mua",
            {
                "PO": po.buyer_name if po else None,
                "Invoice": inv.buyer_name if inv else None,
                "PR": pr.buyer_name if pr else None,
            },
        )

    def rule_address_consistency(self, po: DocumentExtractionData | None,
                                 inv: DocumentExtractionData | None) -> RuleResult:
        problems: list[str] = []
        details: list[dict] = []
        checked = 0

        for field_name in ("seller_address", "buyer_address"):
            po_val = getattr(po, field_name, None) if po else None
            inv_val = getattr(inv, field_name, None) if inv else None
            if po_val and inv_val:
                checked += 1
                match, similarity, diff_tokens = self._matcher.compare_entities(po_val, inv_val)
                if not match:
                    problems.append(
                        f"{field_name}: PO='{po_val}' vs Invoice='{inv_val}' (sim={similarity:.3f})"
                    )
                    details.append(
                        {
                            "field": field_name,
                            "po": po_val,
                            "invoice": inv_val,
                            "similarity": similarity,
                            "diff_tokens": diff_tokens,
                        }
                    )
        if problems:
            return self._result("R10", RuleStatus.FAILED, "; ".join(problems), details={"mismatches": details})
        if checked == 0:
            return self._result("R10", RuleStatus.SKIPPED, "Thiếu địa chỉ ở cả PO và Invoice.")
        return self._result("R10", RuleStatus.PASSED, "Địa chỉ nhất quán giữa PO và Invoice.")

    # -------------------------------------------------------------- R11

    def rule_date_chronology(self, po: DocumentExtractionData | None,
                            inv: DocumentExtractionData | None,
                            pr: DocumentExtractionData | None) -> RuleResult:
        dates = {
            "PO": po.issue_date if po else None,
            "Invoice": inv.issue_date if inv else None,
            "PR": pr.issue_date if pr else None,
        }
        present = {k: v for k, v in dates.items() if v is not None}
        if len(present) < 2:
            return self._result("R11", RuleStatus.SKIPPED, "Thiếu ngày để kiểm tra trình tự thời gian.")

        problems: list[str] = []
        details: list[dict] = []
        order = ["PO", "Invoice", "PR"]
        prev_label, prev_val = None, None
        for label in order:
            val = dates[label]
            if val is None:
                continue
            if prev_val is not None and val < prev_val:
                problems.append(f"Ngày {label} ({val}) trước Ngày {prev_label} ({prev_val})")
                details.append({"earlier": prev_label, "earlier_date": str(prev_val), "later": label, "later_date": str(val)})
            prev_label, prev_val = label, val

        # Hạn thanh toán (nếu có) phải sau ngày Invoice.
        due = (inv.due_date if inv else None) or (pr.due_date if pr else None)
        inv_date = dates["Invoice"]
        if due and inv_date and due < inv_date:
            problems.append(f"Hạn thanh toán ({due}) trước ngày hoá đơn ({inv_date})")
            details.append({"due_date": str(due), "invoice_date": str(inv_date)})

        if problems:
            return self._result("R11", RuleStatus.FAILED, "; ".join(problems), details={"checks": details})
        return self._result("R11", RuleStatus.PASSED, "Trình tự thời gian PO ≤ Invoice ≤ PR hợp lệ.")

    # -------------------------------------------------------------- R12

    def rule_approval_status(self, po: DocumentExtractionData | None,
                             inv: DocumentExtractionData | None,
                             pr: DocumentExtractionData | None) -> RuleResult:
        pending = {"pending", "cho duyet", "chua duyet", "submitted", "draft", "rejected", "tu choi"}
        problems: list[str] = []
        details: list[dict] = []
        checked = 0

        for label, doc in (("PO", po), ("Invoice", inv), ("PR", pr)):
            status = doc.approval_status if doc else None
            if not status:
                continue
            checked += 1
            norm = status.strip().lower()
            if norm in pending or "pending" in norm or "cho" in norm:
                problems.append(f"{label} đang ở trạng thái '{status}' (chưa hoàn tất phê duyệt)")
                details.append({"doc": label, "status": status})

        if problems:
            return self._result("R12", RuleStatus.FAILED, "; ".join(problems), details={"checks": details})
        if checked == 0:
            return self._result("R12", RuleStatus.SKIPPED, "Không có trạng thái phê duyệt để kiểm tra.")
        return self._result("R12", RuleStatus.PASSED, "Trạng thái phê duyệt hợp lệ.")

    # ------------------------------------------------------------- Verdict

    def _verdict(self, results: list[RuleResult]) -> VerdictResult:
        counts: dict[Severity, int] = {s: 0 for s in Severity}
        failed = [r for r in results if r.status == RuleStatus.FAILED]
        for r in failed:
            counts[r.severity] += 1

        if counts[Severity.CRITICAL] or counts[Severity.HIGH]:
            verdict = Verdict.REJECTED
        elif counts[Severity.MEDIUM]:
            verdict = Verdict.WARNING
        else:
            verdict = Verdict.PASSED

        parts: list[str] = []
        for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            if counts[sev]:
                parts.append(f"{counts[sev]} {sev.value}")
        summary = (
            f"Kết quả: {verdict.value}. "
            + ("Vi phạm: " + ", ".join(parts) if parts else "Không có vi phạm.")
        )
        return VerdictResult(
            overall_verdict=verdict,
            summary_note=summary,
            counts_by_severity={s.value: counts[s] for s in Severity},
            critical_count=counts[Severity.CRITICAL],
            high_count=counts[Severity.HIGH],
            medium_count=counts[Severity.MEDIUM],
        )

    # ---------------------------------------------------------------- run

    def run(self, docs: dict[DocType, DocumentExtractionData | None]) -> tuple[VerdictResult, list[RuleResult]]:
        po, inv, pr = docs.get(DocType.PO), docs.get(DocType.INVOICE), docs.get(DocType.PAYMENT_REQUEST)

        rules: list[tuple[str, Callable[[], RuleResult]]] = [
            ("R0", lambda: self.rule_missing_document(docs)),
            ("R1", lambda: self.rule_po_invoice_ref_match(po, inv, pr)),
            ("R2", lambda: self.rule_beneficiary_fraud_check(po, inv, pr)),
            ("R3", lambda: self.rule_line_item_math(po, inv, pr)),
            ("R4", lambda: self.rule_subtotal_vat_total(po, inv, pr)),
            ("R5", lambda: self.rule_item_quantity_match(po, inv)),
            ("R6", lambda: self.rule_item_price_match(po, inv)),
            ("R7", lambda: self.rule_total_amount_match(po, inv, pr)),
            ("R8", lambda: self.rule_seller_name_similarity(po, inv, pr)),
            ("R9", lambda: self.rule_buyer_name_similarity(po, inv, pr)),
            ("R10", lambda: self.rule_address_consistency(po, inv)),
            ("R11", lambda: self.rule_date_chronology(po, inv, pr)),
            ("R12", lambda: self.rule_approval_status(po, inv, pr)),
        ]

        results: list[RuleResult] = []
        for rule_id, fn in rules:
            try:
                results.append(fn())
            except Exception as exc:  # noqa: BLE001 - 1 rule hong khong duoc lam hong ca batch
                logger.exception("Rule %s that bai", rule_id)
                results.append(
                    RuleResult(
                        rule_id=rule_id,
                        rule_name=RULE_NAMES[rule_id],
                        status=RuleStatus.FAILED,
                        severity=Severity.HIGH,
                        message=f"Lỗi quy tắc ngoài ý muốn: {exc}",
                        details={},
                    )
                )
        results.sort(key=lambda r: (list(RULE_SEVERITY).index(r.rule_id) if r.rule_id in RULE_SEVERITY else 99))
        verdict = self._verdict(results)
        return verdict, results


def audit_documents(docs: dict[DocType, DocumentExtractionData | None]) -> tuple[VerdictResult, list[RuleResult]]:
    """Tiện ích: gọi AuditEngine().run(docs)."""
    return AuditEngine().run(docs)
