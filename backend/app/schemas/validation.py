"""Schema cho Validation Engine (R0 - R12) va Verdict tong hop."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class Verdict(str, Enum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    REJECTED = "REJECTED"


class RuleStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Finding(BaseModel):
    """Mot vi pham cua mot quy tac."""

    rule_id: str
    rule_name: str
    status: RuleStatus = RuleStatus.PASSED
    severity: Severity = Severity.INFO
    field_name: str | None = None
    expected_value: str | None = None
    actual_value: str | None = None
    reason: str
    suggestion: str | None = None
    evidence_snippet: str | None = None


class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    status: RuleStatus
    severity: Severity
    message: str
    details: dict = Field(default_factory=dict)


class VerdictResult(BaseModel):
    overall_verdict: Verdict
    summary_note: str
    counts_by_severity: dict[str, int]
    critical_count: int
    high_count: int
    medium_count: int


class AuditBatchRead(BaseModel):
    id: str
    created_at: datetime
    status: str
    overall_verdict: str
    summary_note: str | None = None
    document_count: int = 0


class DocumentRead(BaseModel):
    id: str
    doc_type: str
    file_name: str
    extraction_method: str | None = None
    extraction_model: str | None = None
    degraded: bool = False
    created_at: datetime
    extracted: dict


class FindingRead(BaseModel):
    rule_id: str
    rule_name: str
    status: str
    severity: str
    field_name: str | None = None
    expected_value: str | None = None
    actual_value: str | None = None
    reason: str
    suggestion: str | None = None


class AuditBatchDetail(BaseModel):
    batch: AuditBatchRead
    documents: list[DocumentRead]
    findings: list[FindingRead]
    rule_results: list[RuleResult]
    verdict: VerdictResult
