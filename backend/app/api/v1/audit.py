"""API v1: upload batch, list batches, chi tiet batch."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.extraction import DocType
from app.schemas.validation import SEVERITY_ORDER, Severity
from app.services.audit_pipeline import (
    RULE_HIGHLIGHT,
    _suggestion_for,
    get_batch_detail,
    list_batches,
    process_files,
    save_batch,
)
from app.services.audit_engine import AuditEngine
from app.services.extractor import ExtractorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["audit"])

ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/audit/upload")
async def upload_batch(
    files: list[UploadFile] = File(  # noqa: B008 - FastAPI requires default here
        ..., description="Tối thiểu 1 tệp, tối đa 10 tệp. Mỗi tệp: PDF/ảnh, tối đa 20MB."
    ),
    reference_label: str | None = Form(default=None, description="Số/tiêu đề bộ chứng từ nhập từ UI."),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Upload 1 batch chung tu -> trich xuat -> audit R0-R12 -> luu lich su."""
    label = (reference_label or "").strip() or None
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="Cần tải lên ít nhất 1 tệp.")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Tối đa 10 tệp cho mỗi bộ.")

    allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
    payload: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "document.pdf"
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"Định dạng tệp không được hỗ trợ cho \"{name}\": chỉ chấp nhận {allowed}.",
            )
        content = await f.read()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Tệp {name} vượt quá 20MB.")
        payload.append((name, content))

    # Cho phép người dùng ghi đè gợi ý qua query string ?type_<index>=PO|INVOICE|PAYMENT_REQUEST
    # nhưng mặc định hệ thống tự suy luận.

    outcome = await process_files(payload, extractor=ExtractorService())

    # Tính lại findings để trả đầy đủ ruleResults (không chỉ mức độ nghiêm trọng).
    docs = {d.extraction.data.doc_type: d.extraction.data for d in outcome.processed}
    for k in (DocType.PO, DocType.INVOICE, DocType.PAYMENT_REQUEST):
        docs.setdefault(k, None)
    verdict, rule_results = AuditEngine().run(docs)  # type: ignore[arg-type]
    outcome.verdict = verdict
    outcome.rule_results = rule_results

    batch_id = await save_batch(session, outcome, reference_label=label)

    documents = [
        {
            "file_name": p.file_name,
            "doc_type": p.extraction.data.doc_type.value,
            "extraction_method": p.extraction.layer,
            "extraction_model": p.extraction.model,
            "warnings": p.extraction.warnings,
            "extracted": p.extraction.data.model_dump(mode="json"),
        }
        for p in outcome.processed
    ]

    def _hl(rule_id: str) -> list[str]:
        rid = (rule_id or "").split("_")[0]
        return RULE_HIGHLIGHT.get(rid, [])

    findings_sorted = sorted(
        [f for f in rule_results if f.status.value == "FAILED"],
        key=lambda x: (SEVERITY_ORDER.get(Severity(x.severity.value), 99), x.rule_id),
    )
    return {
        "batch_id": str(batch_id),
        "status": "COMPLETED",
        "reference_label": label,
        "overall_verdict": verdict.overall_verdict.value,
        "summary_note": verdict.summary_note,
        "counts_by_severity": verdict.counts_by_severity,
        "documents": documents,
        "findings": [
            {
                "rule_id": f.rule_id,
                "rule_name": f.rule_name,
                "severity": f.severity.value,
                "field_name": f.details.get("field") or f.details.get("check"),
                "expected_value": str(f.details.get("expected_value") or f.details.get("expected", "")) or None,
                "actual_value": str(f.details.get("actual_value") or f.details.get("actual", "")) or None,
                "reason": f.message,
                "suggestion": _suggestion_for(f.rule_id.split("_")[0]),
                "highlight_targets": _hl(f.rule_id),
                "evidence_snippet": str(f.details)[:1200] if f.details else None,
            }
            for f in findings_sorted
        ],
        "rule_results": [
            {"rule_id": r.rule_id, "rule_name": r.rule_name, "status": r.status.value,
             "severity": r.severity.value, "message": r.message, "details": r.details}
            for r in rule_results
        ],
        "verdict": verdict.model_dump(),
    }


@router.get("/audit/batches")
async def list_audit_batches(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_batches(session, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/audit/batches/{batch_id}")
async def get_audit_batch(batch_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    try:
        uid = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="batch_id không hợp lệ") from None
    detail = await get_batch_detail(session, uid)
    if detail is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ dữ liệu")
    # Bổ sung rule_results ở trang chi tiết (tính lại từ extracted_json đã lưu).
    from app.schemas.extraction import DocumentExtractionData as _D  # noqa: PLC0415

    docs = {DocType.PO: None, DocType.INVOICE: None, DocType.PAYMENT_REQUEST: None}
    for d in detail["documents"]:
        try:
            data = _D.model_validate(d["extracted"])
            docs[data.doc_type] = data
        except Exception:  # noqa: BLE001
            logger.warning("Không phân tích lại được extracted_json cho %s", d["file_name"])
    verdict, rule_results = AuditEngine().run(docs)  # type: ignore[arg-type]
    detail["rule_results"] = [
        {"rule_id": r.rule_id, "rule_name": r.rule_name, "status": r.status.value,
         "severity": r.severity.value, "message": r.message, "details": r.details}
        for r in rule_results
    ]
    detail["verdict"] = verdict.model_dump()

    # Bổ sung suggestion + highlight_targets cho findings đã lưu trong DB
    # để UI hiển thị lịch sử vẫn đủ thông tin như đợt tải mới.
    for f in detail.get("findings", []):
        rid = (f.get("rule_id") or "").split("_")[0]
        f.setdefault("suggestion", _suggestion_for(rid))
        f["highlight_targets"] = RULE_HIGHLIGHT.get(rid, [])
    detail["findings"] = sorted(
        detail["findings"],
        key=lambda x: SEVERITY_ORDER.get(Severity(x.get("severity", "INFO")), 99),
    )
    return detail


@router.get("/audit/batches/{batch_id}/export")
async def export_batch_csv(batch_id: str, session: AsyncSession = Depends(get_db)) -> Response:
    """Xuất tệp CSV findings cho bộ dữ liệu. Dùng để đính kèm báo cáo kiểm tra."""
    try:
        uid = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="batch_id không hợp lệ") from None
    detail = await get_batch_detail(session, uid)
    if detail is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ dữ liệu")

    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rule_id", "severity", "field", "expected", "actual", "reason", "suggestion"])
    for f in detail["findings"]:
        w.writerow([f["rule_id"], f["severity"], f.get("field_name", ""), f.get("expected_value", ""), f.get("actual_value", ""), f["reason"], f.get("suggestion", "")])
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=audit-{batch_id}.csv"},
    )

