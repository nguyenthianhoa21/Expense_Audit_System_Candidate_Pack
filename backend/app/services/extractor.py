"""Extraction Engine: chi doc tai lieu, khong phan doan kiem toan.

Kien truc 4 lop phong ve (Failover):

    Layer 1  Config Guard      -> thieu OPENROUTER_API_KEY / file không đọc được
    Layer 2  Model Chain       -> gemma-4-31b-it:free  ->  gemma-4-26b-a4b-it:free
    Layer 3  Retry & Timeout   -> exponential backoff, toi da 3 lan, timeout 20s
    Layer 4  Offline Parser    -> pdfplumber/PyMuPDF + regex, luon co ket qua

Ke hoach ban giao:
    ExtractionResult.data      -> DocumentExtractionData (Pydantic v2)
    ExtractionResult.degraded  -> True neu phai ra toi Layer 4
    ExtractionResult.warnings  -> mo ta ly do fallback cho UI/README
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.schemas.extraction import DocType, DocumentExtractionData
from app.services.document_io import read_document_text, validate_document_input
from app.services.offline_parser import detect_doc_type, parse_offline_plain_text

logger = logging.getLogger(__name__)

# ------------------------------------------------------ helpers cho giao dien
# Nguyen tac: loi ky thuat chi ghi log o terminal, khong day thang len UI.
_RATE_LIMIT_HINTS = ("429", "rate-limited", "rate limited", "ratelimit")


def _sanitize_ui_text(text: str, limit: int = 200) -> str:
    """ rut gon chuoi loi tho cho hien thi tren FE (bo JSON tho, cat ngan). """
    t = (text or "").strip()
    if not t:
        return ""
    # Cat phan JSON tho {"error": ...} neu xuat hien som.
    cut = t.find("{")
    if 0 < cut <= 60:
        t = t[:cut].strip().rstrip(";,")
    if len(t) > limit:
        t = t[:limit].rstrip() + "\u2026"
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _friendly_model_warning(model: str, exc: Exception) -> str:
    """ Thay loi tho cua OpenRouter bang thong bao tieng Viet de doc. """
    raw = str(exc)
    low = raw.lower()
    if any(h in low for h in _RATE_LIMIT_HINTS) or "HTTP 429" in raw:
        return (
            f"{model}: provider dang gioi han toc do (HTTP 429), "
            "da het so lan thu. He thong chuyen sang bo phan tich du phong cuc bo."
        )
    return f"{model}: { _sanitize_ui_text(raw, 180) }".strip()


SYSTEM_PROMPT = """Ban la chuyen gia trich xuat du lieu chung tu tai lieu doanh nghiep (PO / Invoice / Payment Request).

QUY TAC BAT BUOC:
1. CHI sao chei dung thong tin co trong tai lieu. TUYET DOI khong suy dien, khong tinh toan lai, khong tu "sua" cho dung.
   Neu quantity * unit_price != amount trong tai lieu, van ghi nguyen gia tri goc - viec kiem tra se do Validation Engine dam nhan.
2. Chi tra ve MOT doi tuong JSON duy nhat, khong co markdown, khong code fence, khong giai thich.
3. Ngay thang theo dinh dang YYYY-MM-DD.
4. Tien te: ma chuan 3 chu (VND, USD, EUR).
5. So tien: so thuan (khong co dau phay hay dau cham), vi du 3200000.
6. Truong khong co trong tai lieu -> null (khong doan).
7. Giu nguyen tieng Viet co dau trong ten cong ty, dia chi, mo ta hang hoa.

SCHEMA JSON (dung duoc key nay, them key khac se bi bo qua):
{
  "doc_type": "PO | INVOICE | PAYMENT_REQUEST",
  "doc_number": "string | null",
  "reference_numbers": ["string"],
  "issue_date": "YYYY-MM-DD | null",
  "buyer_name": "string | null",
  "buyer_address": "string | null",
  "seller_name": "string | null",
  "seller_address": "string | null",
  "requester_name": "string | null",
  "department": "string | null",
  "payment_purpose": "string | null",
  "currency": "string | null",
  "items": [
    {"item_code": "string | null", "description": "string | null", "quantity": "number | null",
     "unit": "string | null", "unit_price": "number | null", "amount": "number | null"}
  ],
  "subtotal_amount": "number | null",
  "vat_rate": "number | null",
  "vat_amount": "number | null",
  "total_amount": "number | null",
  "requested_payment_amount": "number | null",
  "bank_beneficiary": {
    "account_name": "string | null", "account_number": "string | null", "bank_name": "string | null"
  },
  "due_date": "YYYY-MM-DD | null",
  "approval_status": "string | null"
}

YEU CAU THEO LOAI CHUNG TU:
- PO: doc hang "PO Number", "Bên mua", "Bên bán", "Chi tiết đặt hàng", "Điều kiện đặt hàng", "Thông tin thanh toán nhà cung cấp", "Trạng thái".
- INVOICE: doc hang "Số hóa đơn", "Tham chiếu đơn hàng", "Seller / Bên bán", "Bill To / Bên mua", "Subtotal", "VAT", "Total Due", "Payment Information", "Due date".
- PAYMENT_REQUEST: doc hang "Số đề nghị", "Người đề nghị", "Phòng ban", "Nhà cung cấp", "Số PO", "Số hóa đơn",
  "Giá trị hóa đơn", "Số tiền đề nghị thanh toán", "Thông tin người thụ hưởng", "Phê duyệt".
"""


@dataclass(slots=True)
class ExtractionResult:
    data: DocumentExtractionData
    model: str | None = None
    degraded: bool = False
    layer: str = "LLM"
    elapsed_ms: int = 0
    attempts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExtractionError(RuntimeError):
    pass


class ExtractorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ---------------------------------------------------------- helpers

    def _headers(self) -> dict[str, str]:
        s = self.settings
        headers = {
            "Authorization": f"Bearer {s.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        if s.OPENROUTER_APP_URL:
            headers["HTTP-Referer"] = s.OPENROUTER_APP_URL
        if s.OPENROUTER_APP_TITLE:
            headers["X-Title"] = s.OPENROUTER_APP_TITLE
        return headers

    def _response_format(self) -> dict[str, Any]:
        mode = (self.settings.OPENROUTER_RESPONSE_FORMAT or "json_object").lower()
        if mode == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_extraction",
                    "strict": False,
                    "schema": self._json_schema(),
                },
            }
        if mode == "json_object":
            return {"type": "json_object"}
        return {}

    def _json_schema(self) -> dict[str, Any]:
        def num() -> dict[str, Any]:
            return {"type": ["number", "null"]}

        def txt() -> dict[str, Any]:
            return {"type": ["string", "null"]}

        return {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string", "enum": ["PO", "INVOICE", "PAYMENT_REQUEST"]},
                "doc_number": txt(),
                "reference_numbers": {"type": "array", "items": {"type": "string"}},
                "issue_date": txt(),
                "buyer_name": txt(),
                "buyer_address": txt(),
                "seller_name": txt(),
                "seller_address": txt(),
                "requester_name": txt(),
                "department": txt(),
                "payment_purpose": txt(),
                "currency": txt(),
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_code": txt(),
                            "description": txt(),
                            "quantity": num(),
                            "unit": txt(),
                            "unit_price": num(),
                            "amount": num(),
                        },
                    },
                },
                "subtotal_amount": num(),
                "vat_rate": num(),
                "vat_amount": num(),
                "total_amount": num(),
                "requested_payment_amount": num(),
                "bank_beneficiary": {
                    "type": ["object", "null"],
                    "properties": {
                        "account_name": txt(),
                        "account_number": txt(),
                        "bank_name": txt(),
                    },
                },
                "due_date": txt(),
                "approval_status": txt(),
            },
        }

    @staticmethod
    def _build_user_prompt(text: str, hint: DocType | None) -> str:
        head = "Loai chung tu duoc ky vong: " + hint.value + "\n\n" if hint else ""
        return (
            f"{head}Noi dung tai lieu:\n\"\"\"\n{text}\n\"\"\"\n\n"
            "Tra ve JSON theo dung schema da cho."
        )

    @staticmethod
    def _parse_model_json(content: str) -> dict[str, Any]:
        raw = content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise ExtractionError("Mô hình trả về nội dung không phải JSON")
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"JSON không hợp lệ: {exc}") from exc

    # ------------------------------------------- Layer 2 + 3 (LLM call)

    async def _call_model_once(
        self, client: httpx.AsyncClient, model: str, messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
        }
        rf = self._response_format()
        if rf:
            payload["response_format"] = rf

        response = await client.post("/chat/completions", json=payload, headers=self._headers())
        if response.status_code >= 400:
            body = response.text[:400]
            raise ExtractionError(f"HTTP {response.status_code}: {body}")

        body = response.json()
        if body.get("error"):
            raise ExtractionError(f"API error: {body['error']}")
        choices = body.get("choices") or []
        if not choices:
            raise ExtractionError("Phản hồi không có danh sách lựa chọn")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise ExtractionError("Noi dung tra ve rong")
        return self._parse_model_json(content)

    async def _call_model_with_retry(
        self,
        model: str,
        text: str,
        hint: DocType | None,
        client: httpx.AsyncClient,
        attempts: list[str],
    ) -> DocumentExtractionData:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(text, hint)},
        ]
        max_retries = max(1, self.settings.MAX_RETRIES)
        timeout = self.settings.REQUEST_TIMEOUT_SECONDS
        base = max(0.1, self.settings.BACKOFF_BASE_SECONDS)

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                raw = await self._call_model_once(client, model, messages)
                attempts.append(f"{model}: OK (lan {attempt})")
                data = DocumentExtractionData.model_validate(raw)
                if hint and data.doc_type != hint:
                    attempts.append(f"{model}: doc_type model={data.doc_type} != hint={hint.value}")
                return data
            except (httpx.TimeoutException, httpx.TransportError, ExtractionError) as exc:
                last_error = exc
                attempts.append(f"{model}: loi lan {attempt} - {type(exc).__name__}: {exc}")
                logger.warning("OpenRouter %s that bai (lan %d/%d): %s", model, attempt, max_retries, exc)
                if attempt < max_retries:
                    await asyncio.sleep(base * (2 ** (attempt - 1)))

        raise ExtractionError(f"Het so lan retry cho model {model}: {last_error}")

    # ------------------------------------------ Layer 4 (offline parser)

    def _offline(self, text: str, hint: DocType | None, reason: str, elapsed_ms: int) -> ExtractionResult:
        doc_type = hint or detect_doc_type(text)
        data = parse_offline_plain_text(text, doc_type)
        missing = [
            name
            for name in ("doc_number", "issue_date", "total_amount", "buyer_name", "seller_name")
            if getattr(data, name) in (None, "")
        ]
        warnings = [f"Offline parser (Layer 4) vi: {reason}"]
        if not data.items:
            warnings.append("Khong tach duoc dong hang - can nguoi dung kiem tra lai bang mat.")
        if missing:
            warnings.append("Truong rong sau khi phan tich du phong: " + ", ".join(missing))
        return ExtractionResult(
            data=data,
            model=None,
            degraded=True,
            layer="OFFLINE_FALLBACK",
            elapsed_ms=elapsed_ms,
            warnings=warnings,
        )

    # ------------------------------------------------------------ main

    async def extract(
        self, content: bytes, filename: str, doc_type_hint: DocType | None = None
    ) -> ExtractionResult:
        started = time.perf_counter()
        warnings: list[str] = []

        # Layer 1a - input guard
        validate_document_input(content, filename, self.settings.MAX_UPLOAD_MB)
        text, meta = await asyncio.to_thread(read_document_text, content, filename)
        if not text.strip():
            raise ExtractionError(
                f"{filename}: không trích được văn bản. Tệp scan/ảnh không có lớp văn bản "
                "cần OCR trước khi đưa vào hệ thống."
            )

        # Layer 1b - config guard
        if not self.settings.OPENROUTER_API_KEY:
            warnings.append("Thiếu OPENROUTER_API_KEY (Lớp 1 - Bảo vệ cấu hình)")
            result = self._offline(text, doc_type_hint, "thieu OPENROUTER_API_KEY", self._elapsed(started))
            result.warnings = warnings + result.warnings
            result.attempts = [f"{filename}: {meta['pages']} trang, {meta['backend']}"]
            return result

        timeout = httpx.Timeout(self.settings.REQUEST_TIMEOUT_SECONDS, connect=10.0)
        attempts: list[str] = [f"{filename}: {meta['pages']} trang, doc bang {meta['backend']}"]
        chain = self.settings.model_chain or ["google/gemma-4-31b-it:free"]

        async with httpx.AsyncClient(base_url=self.settings.OPENROUTER_BASE_URL, timeout=timeout) as client:
            for model in chain:
                try:
                    data = await self._call_model_with_retry(model, text, doc_type_hint, client, attempts)
                except ExtractionError as exc:
                    warnings.append(_friendly_model_warning(model, exc))
                    logger.warning("Bo qua model %s, chuyen sang model tiep theo", model)
                    continue

                elapsed = self._elapsed(started)
                result = ExtractionResult(
                    data=data,
                    model=model,
                    degraded=False,
                    layer="LLM",
                    elapsed_ms=elapsed,
                    attempts=attempts,
                    warnings=warnings,
                )
                if meta["pages"] > 1:
                    result.warnings.append(
                        f"Tai lieu {meta['pages']} trang: da gui toan bo van ban, hay doi chieu lai"
                    )
                return result

        # Layer 4 - phan tich du phong cuc bo
        reasons = _sanitize_ui_text("; ".join(warnings), 240) or "Tat ca mo hinh trong chuoi deu that bai"
        logger.warning("Layer 4 fallback (Offline parser): %s", reasons)
        result = self._offline(text, doc_type_hint, reasons, self._elapsed(started))
        result.warnings = warnings + result.warnings
        result.attempts = attempts
        return result

    @staticmethod
    def _elapsed(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)


extractor_service = ExtractorService()
