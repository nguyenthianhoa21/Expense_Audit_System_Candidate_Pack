"""Smoke test offline (không cần API key): parser + audit engine + verdict.

Chay: python scripts/smoke_offline.py
"""
from __future__ import annotations

import os, sys, pathlib
# force UTF-8 output on Windows so print() does not crash on Vietnamese
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
   pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.schemas.extraction import DocType  # noqa: E402
from app.services.audit_engine import AuditEngine  # noqa: E402
from app.services.document_io import read_document_text  # noqa: E402
from app.services.offline_parser import parse_offline_plain_text  # noqa: E402

SAMPLE_DIR = pathlib.Path(__file__).resolve().parents[2] / "Sample"
FILES = {
    DocType.PO: "Sample_Purchase_Order.pdf",
    DocType.INVOICE: "Sample_Invoice.pdf",
    DocType.PAYMENT_REQUEST: "Sample_Payment_Request.pdf",
}


def main() -> int:
    docs = {}
    for dtype, name in FILES.items():
        path = SAMPLE_DIR / name
        text, meta = read_document_text(path.read_bytes(), name)
        data = parse_offline_plain_text(text)
        docs[dtype] = data
        print(f"[{dtype.value:16}] {name} pages={meta['pages']} no={data.doc_number} "
              f"total={data.total_amount} req={data.requested_payment_amount} items={len(data.items)}")

    verdict, results = AuditEngine().run(docs)
    print()
    print(f"VERDICT = {verdict.overall_verdict.value}")
    print(f"SUMMARY = {verdict.summary_note}")
    print()
    for r in results:
        mark = "FAIL" if r.status.value == "FAILED" else r.status.value
        print(f"  [{mark:5}] {r.rule_id:3} {r.rule_name:38} {r.severity.value:8} {r.message[:100]}")

    ok = verdict.overall_verdict.value == "REJECTED"
    print()
    print("Kỳ vọng REJECTED (bộ mẫu cố ý chứa lỗi):", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())