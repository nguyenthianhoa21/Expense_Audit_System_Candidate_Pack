"""Pipeline: upload -> luu file -> phan loai + trich xuat -> audit R0-R12 -> luu DB."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import models as m
from app.schemas.extraction import DocType, DocumentExtractionData
from app.schemas.validation import RuleResult, Severity, Verdict, VerdictResult
from app.services.audit_engine import AuditEngine
from app.services.extractor import ExtractionResult, ExtractorService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessedDocument:
    file_name: str
    file_path: str
    extraction: ExtractionResult


@dataclass(slots=True)
class BatchOutcome:
    batch_id: uuid.UUID
    verdict: VerdictResult
    rule_results: list[RuleResult]
    processed: list[ProcessedDocument] = field(default_factory=list)


DOC_TYPE_FROM_SUFFIX = {
    "po": DocType.PO,
    "purchase": DocType.PO,
    "invoice": DocType.INVOICE,
    "inv": DocType.INVOICE,
    "payment": DocType.PAYMENT_REQUEST,
    "request": DocType.PAYMENT_REQUEST,
    "pr": DocType.PAYMENT_REQUEST,
}


def guess_doc_type_hint(filename: str) -> DocType | None:
    """Phân loại sơ bộ tu ten file (người dùng co the ghi de o UI)."""
    low = filename.lower()
    for key, dtype in DOC_TYPE_FROM_SUFFIX.items():
        if key in low:
            return dtype
    return None


async def process_files(
    files: list[tuple[str, bytes]],
    extractor: ExtractorService | None = None,
    hints: dict[str, DocType] | None = None,
) -> BatchOutcome:
    """Chạy trích xuất + audit cho 1 batch upload, chua luu DB."""
    settings = get_settings()
    extractor = extractor or ExtractorService()
    storage = Path(settings.STORAGE_PATH)
    batch_id = uuid.uuid4()
    batch_dir = storage / str(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    processed: list[ProcessedDocument] = []
    for filename, content in files:
        safe = Path(filename).name or f"document-{len(processed) + 1}.pdf"
        dest = batch_dir / safe
        # Tránh ghi đè khi trùng tên tệp.
        counter = 1
        while dest.exists():
            dest = batch_dir / f"{dest.stem}-{counter}{dest.suffix}"
            counter += 1
        dest.write_bytes(content)

        hint = (hints or {}).get(filename) or guess_doc_type_hint(safe)
        extraction = await extractor.extract(content, safe, hint)
        processed.append(ProcessedDocument(file_name=safe, file_path=str(dest), extraction=extraction))

    docs: dict[DocType, DocumentExtractionData | None] = {
        DocType.PO: None,
        DocType.INVOICE: None,
        DocType.PAYMENT_REQUEST: None,
    }
    duplicates: list[str] = []
    for p in processed:
        dtype = p.extraction.data.doc_type
        if docs[dtype] is None:
            docs[dtype] = p.extraction.data
        else:
            duplicates.append(f"{p.file_name} cùng là {dtype.value}, chỉ dùng tệp đầu tiên cho kiểm tra")

    verdict, rule_results = AuditEngine().run(docs)
    if duplicates:
        # Ghi nhận tệp thừa ở mức INFO để UI hiển thị, không ảnh hưởng kết luận.
        rule_results.append(
            RuleResult(
                rule_id="DUP",
                rule_name="DUPLICATE_DOCUMENT_TYPE",
                status="PASSED",
                severity=Severity.INFO,
                message="; ".join(duplicates),
                details={"duplicates": duplicates},
            )
        )
    return BatchOutcome(batch_id=batch_id, verdict=verdict, rule_results=rule_results, processed=processed)


def _finding_rows(batch_id: uuid.UUID, results: list[RuleResult]) -> list[m.ValidationFinding]:
    rows: list[m.ValidationFinding] = []
    for r in results:
        if r.status.value != "FAILED" and r.rule_id != "DUP":
            continue
        if r.rule_id == "DUP":
            rows.append(
                m.ValidationFinding(
                    batch_id=batch_id,
                    rule_id="DUP",
                    severity=Severity.INFO.value,
                    field_name=None,
                    expected_value=None,
                    actual_value=None,
                    reason=r.message,
                    suggestion="Kiểm tra lại tệp đã tải, mỗi loại chứng từ chỉ cần 1 tệp.",
                    evidence_snippet=None,
                )
            )
            continue
        details = r.details or {}
        expected = details.get("expected_value") or details.get("expected")
        actual = details.get("actual_value") or details.get("actual")
        rows.append(
            m.ValidationFinding(
                batch_id=batch_id,
                rule_id=f"{r.rule_id}_{r.rule_name}",
                severity=r.severity.value,
                field_name=details.get("field") or details.get("check"),
                expected_value=str(expected) if expected is not None else None,
                actual_value=str(actual) if actual is not None else None,
                reason=r.message,
                suggestion=_suggestion_for(r.rule_id),
                evidence_snippet=str(details)[:2000] if details else None,
            )
        )
    return rows


# Nguồn duy nhất cho gợi ý hiển thị: rule -> các ô dữ liệu cần tô sáng.
# Định dạng: "<DOC_TYPE>::<field_path>" (field_path la key trong extracted JSON).
RULE_HIGHLIGHT: dict[str, list[str]] = {
    "R0": ["PO::doc_number", "INVOICE::doc_number", "PAYMENT_REQUEST::doc_number"],
    "R1": ["INVOICE::reference_numbers", "PAYMENT_REQUEST::reference_numbers", "PO::doc_number"],
    "R2": [
        "PAYMENT_REQUEST::bank_beneficiary.account_number",
        "PAYMENT_REQUEST::bank_beneficiary.account_name",
        "INVOICE::bank_beneficiary.account_number",
        "PO::bank_beneficiary.account_number",
        "PAYMENT_REQUEST::bank_beneficiary.account_name",
        "INVOICE::bank_beneficiary.account_name",
    ],
    "R3": ["INVOICE::items", "PO::items", "INVOICE::items.__table", "PO::items.__table"],
    "R4": ["INVOICE::subtotal_amount", "INVOICE::vat_amount", "INVOICE::total_amount", "PO::subtotal_amount", "PO::total_amount", "PO::subtotal_amount", "INVOICE::subtotal_amount"],
    "R5": ["INVOICE::items", "PO::items", "INVOICE::items.__table", "PO::items.__table"],
    "R6": ["INVOICE::items", "PO::items", "INVOICE::items.__table", "PO::items.__table"],
    "R7": ["PO::total_amount", "INVOICE::total_amount", "PAYMENT_REQUEST::requested_payment_amount"],
    "R8": ["PO::seller_name", "INVOICE::seller_name", "PAYMENT_REQUEST::seller_name"],
    "R9": ["PO::buyer_name", "INVOICE::buyer_name", "PAYMENT_REQUEST::buyer_name"],
    "R10": ["PO::buyer_address", "PO::seller_address", "INVOICE::buyer_address", "INVOICE::seller_address"],
    "R11": ["PO::issue_date", "INVOICE::issue_date", "PAYMENT_REQUEST::issue_date", "INVOICE::due_date"],
    "R12": ["PO::approval_status", "INVOICE::approval_status", "PAYMENT_REQUEST::approval_status"],
}


def _suggestion_for(rule_id: str) -> str:
    return {
        "R0": "Bổ sung đầy đủ PO, Invoice và Payment Request rồi chạy lại kiểm tra.",
        "R1": "Kiểm tra số PO tham chiếu trên Invoice/PR phải khớp số PO gốc.",
        "R2": "Xác minh tài khoản thụ hưởng với nhà cung cấp; không thanh toán khi chưa khớp.",
        "R3": "Soát lại bảng kê: số lượng × đơn giá phải bằng thành tiền trên từng dòng.",
        "R4": "Soát lại tổng phụ, VAT và tổng trên chứng từ.",
        "R5": "Số lượng trên Invoice không được vượt PO; yêu cầu điều chỉnh hoặc bổ sung PO.",
        "R6": "Đơn giá trên Invoice không được vượt PO; đàm phán lại hoặc điều chỉnh hoá đơn.",
        "R7": "Số tiền đề nghị trên PR phải khớp 100% tổng Invoice; tổng Invoice không vượt PO.",
        "R8": "Kiểm tra tên bên bán trên các chứng từ có đồng nhất không.",
        "R9": "Kiểm tra tên bên mua trên các chứng từ có đồng nhất không.",
        "R10": "Đối chiếu địa chỉ bên mua/bên bán giữa PO và Invoice.",
        "R11": "Kiểm tra trình tự ngày: PO ≤ Invoice ≤ PR và hạn thanh toán.",
        "R12": "Hoàn tất phê duyệt trên PO/PR trước khi thanh toán.",
    }.get(rule_id, "Kiểm tra lại chứng từ liên quan.")


async def save_batch(session: AsyncSession, outcome: BatchOutcome, reference_label: str | None = None) -> uuid.UUID:
    """Lưu bộ dữ liệu + documents + findings vao DB, trả về batch_id."""
    batch = m.AuditBatch(
        id=outcome.batch_id,
        status="COMPLETED",
        overall_verdict=outcome.verdict.overall_verdict.value,
        summary_note=outcome.verdict.summary_note,
        reference_label=reference_label,
    )
    session.add(batch)
    for p in outcome.processed:
        data = p.extraction.data
        session.add(
            m.Document(
                batch_id=outcome.batch_id,
                doc_type=data.doc_type.value,
                file_name=p.file_name,
                file_path=p.file_path,
                extracted_json=data.model_dump(mode="json"),
                extraction_method=p.extraction.layer,
                extraction_model=p.extraction.model,
                extraction_warnings=p.extraction.warnings or None,
            )
        )
    for row in _finding_rows(outcome.batch_id, outcome.rule_results):
        session.add(row)
    await session.commit()
    return outcome.batch_id


async def list_batches(session: AsyncSession, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    total = (await session.execute(select(func.count(m.AuditBatch.id)))).scalar_one()
    rows = (
        await session.execute(
            select(m.AuditBatch).order_by(m.AuditBatch.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    items: list[dict] = []
    for b in rows.all():
        doc_count = (
            await session.execute(select(func.count(m.Document.id)).where(m.Document.batch_id == b.id))
        ).scalar_one()
        created = b.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        items.append(
            {
                "id": str(b.id),
                "created_at": created.isoformat() if created else None,
                "status": b.status,
                "overall_verdict": b.overall_verdict,
                "summary_note": b.summary_note,
                "reference_label": b.reference_label,
                "document_count": doc_count,
            }
        )
    return items, total


async def get_batch_detail(session: AsyncSession, batch_id: uuid.UUID) -> dict | None:
    batch = (await session.execute(select(m.AuditBatch).where(m.AuditBatch.id == batch_id))).scalar_one_or_none()
    if batch is None:
        return None
    docs = (
        await session.execute(select(m.Document).where(m.Document.batch_id == batch_id).order_by(m.Document.created_at))
    ).scalars()
    findings = (
        await session.execute(select(m.ValidationFinding).where(m.ValidationFinding.batch_id == batch_id))
    ).scalars()
    created = batch.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "batch": {
            "id": str(batch.id),
            "created_at": created.isoformat() if created else None,
            "status": batch.status,
            "overall_verdict": batch.overall_verdict,
            "summary_note": batch.summary_note,
            "reference_label": batch.reference_label,
        },
        "documents": [
            {
                "id": str(d.id),
                "doc_type": d.doc_type,
                "file_name": d.file_name,
                "extraction_method": d.extraction_method,
                "extraction_model": d.extraction_model,
                "warnings": d.extraction_warnings or [],
                "extracted": d.extracted_json,
            }
            for d in docs.all()
        ],
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "field_name": f.field_name,
                "expected_value": f.expected_value,
                "actual_value": f.actual_value,
                "reason": f.reason,
                "suggestion": f.suggestion,
            }
            for f in findings.all()
        ],
    }
