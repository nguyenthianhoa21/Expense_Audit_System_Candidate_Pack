"""So khop chuoi van ban mo (ten cong ty, dia chi) cho R8 / R9 / R10.

Thiet ke:
  - Fast-path: chuoi giong het -> MATCH, khong goi model.
  - Tokenize + Clean: bo danh xung phap ly, tach token bang regex [A-Z0-9]+.
  - XOR Token Diff: tokens1 ^ tokens2 de bat sai lech ky tu.
  - Cosine similarity: BGE-M3 (lazy load, Singleton). Neu khong co model tai
    local, tu lui ve token ratio de he thong van chay duoc offline.

Quyet dinh khop: len(diff_tokens) == 0 VA similarity >= 0.995.
"""
from __future__ import annotations

import logging
import re
import threading
from difflib import SequenceMatcher
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)

LEGAL_SUFFIXES: Set[str] = {
    "CONG", "TY", "TNHH", "MTV", "CO", "PHAN", "CP", "JSC", "CORP",
    "CORPORATION", "LIMITED", "LTD", "INC", "GROUP", "DOANH",
}

VN_REPLACEMENTS = {
    "À": "A", "Á": "A", "Ả": "A", "Ã": "A", "Ạ": "A", "Ă": "A", "Ằ": "A",
    "Ắ": "A", "Ẳ": "A", "Ẵ": "A", "Ặ": "A", "Â": "A", "Ầ": "A", "Ấ": "A",
    "Ẩ": "A", "Ẫ": "A", "Ậ": "A", "Đ": "D", "È": "E", "É": "E", "Ẻ": "E",
    "Ẽ": "E", "Ẹ": "E", "Ê": "E", "Ề": "E", "Ế": "E", "Ể": "E", "Ễ": "E",
    "Ệ": "E", "Ì": "I", "Í": "I", "Ỉ": "I", "Ĩ": "I", "Ị": "I", "Ò": "O",
    "Ó": "O", "Ỏ": "O", "Õ": "O", "Ọ": "O", "Ô": "O", "Ồ": "O", "Ố": "O",
    "Ổ": "O", "Ỗ": "O", "Ộ": "O", "Ơ": "O", "Ờ": "O", "Ớ": "O", "Ở": "O",
    "Ỡ": "O", "Ợ": "O", "Ù": "U", "Ú": "U", "Ủ": "U", "Ũ": "U", "Ụ": "U",
    "Ư": "U", "Ừ": "U", "Ứ": "U", "Ử": "U", "Ữ": "U", "Ự": "U", "Ỳ": "Y",
    "Ý": "Y", "Ỷ": "Y", "Ỹ": "Y", "Ỵ": "Y",
}

_TOKEN_RE = re.compile(r"[A-Z0-9]+")


class BGEMatcher:
    """Singleton lazy-loading BGE-M3, tu fallback neu khong co model."""

    SIMILARITY_THRESHOLD = 0.995
    MODEL_NAME = "BAAI/bge-m3"

    _instance: "BGEMatcher | None" = None
    _lock = threading.Lock()

    def __new__(cls, model_name: str = MODEL_NAME) -> "BGEMatcher":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        if getattr(self, "_initialized", False):
            return
        with BGEMatcher._lock:
            if getattr(self, "_initialized", False):
                return
            self.model_name = model_name
            self.model = None
            self.legal_suffixes = set(LEGAL_SUFFIXES)
            self._init_error: str | None = None
            self._initialized = True

    def _ensure_model(self) -> None:
        import os # patched
        if os.environ.get('DISABLE_BGE') == '1':
            if self._init_error is None:
                self._init_error = 'disabled by env'
        if self.model is not None or self._init_error is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Dang load BGE-M3: %s", self.model_name)
            self.model = SentenceTransformer(self.model_name)
            logger.info("Load BGE-M3 thanh cong")
        except Exception as exc:
            self._init_error = str(exc)
            logger.warning(
                "Khong load duoc BGE-M3 (%s). Dung token-based similarity thay the. "
                "Cai dat: pip install sentence-transformers torch",
                exc,
            )

    def _normalize_text(self, text: str) -> str:
        text = (text or "").upper().strip()
        for src, dst in VN_REPLACEMENTS.items():
            text = text.replace(src, dst)
        for ch in ".,;:()[]{}\"'`/\\|-_":
            text = text.replace(ch, " ")
        return re.sub(r"\s+", " ", text).strip()

    def _tokenize_and_clean(self, text: str) -> Set[str]:
        normalized = self._normalize_text(text)
        tokens = set(_TOKEN_RE.findall(normalized))
        return tokens - self.legal_suffixes

    def compare_entities(self, str1: str, str2: str) -> Tuple[bool, float, List[str]]:
        """Tra ve (is_match, similarity, diff_tokens)."""
        if not str1 or not str2:
            return False, 0.0, ["Thieu chuoi so sanh"]

        if str1.strip().lower() == str2.strip().lower():
            return True, 1.0, []

        tokens1 = self._tokenize_and_clean(str1)
        tokens2 = self._tokenize_and_clean(str2)
        diff_tokens = list(tokens1 ^ tokens2)

        similarity = self._cosine(str1, str2)
        is_match = len(diff_tokens) == 0 and similarity >= self.SIMILARITY_THRESHOLD
        return is_match, round(similarity, 4), diff_tokens

    def _cosine(self, str1: str, str2: str) -> float:
        self._ensure_model()
        if self.model is None:
            return self._token_similarity(str1, str2)
        try:
            import numpy as np

            emb = self.model.encode([str1, str2], normalize_embeddings=True)
            return float(np.dot(emb[0], emb[1]))
        except Exception as exc:
            logger.warning("BGE-M3 encode that bai (%s), dung fallback", exc)
            return self._token_similarity(str1, str2)

    def _token_similarity(self, str1: str, str2: str) -> float:
        """Fallback deterministic: so sanh token da chuan hoa (khong can model)."""
        a = self._normalize_text(str1).split()
        b = self._normalize_text(str2).split()
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

