import logging
from io import BytesIO
import pdfplumber

logger = logging.getLogger(__name__)

def read_document_text(raw: bytes, filename: str) -> tuple[str, dict]:
    """Tra ve (text, meta) voi so trang."""
    suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    text, meta = "", {"pages": 0, "backend": None}
    if suffix == "pdf":
        with pdfplumber.open(BytesIO(raw)) as pdf:
            pages = []
            for page in pdf.pages or []:
                try:
                    pages.append(page.extract_text() or "")
                except Exception as exc:
                    logger.warning("pdf page extract failed: %s", exc)
            text = "\n\n".join(pages)
            meta = {"pages": len(pages), "backend": "pdfplumber"}
        if not text.strip():
            try:
                import fitz  # PyMuPDF fallback
                doc = fitz.open(stream=raw, filetype="pdf")
                text = "\n\n".join(p.get_text() for p in doc)
                meta = {"pages": len(doc), "backend": "pymupdf"}
            except Exception as exc:
                logger.warning("pymupdf fallback failed: %s", exc)
    else:
        text = raw.decode("utf-8", errors="replace")
        meta = {"pages": 1, "backend": "raw-text"}
    return text, meta

def validate_document_input(content: bytes, filename: str, max_mb: int) -> None:
    if not content:
        raise ValueError(f"File trong: {filename}")
    if len(content) > max_mb * 1024 * 1024:
        raise ValueError(f"File {filename} vuot qua {max_mb}MB")
