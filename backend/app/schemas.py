from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["pass", "risk", "manual"]
EffectiveStatus = Literal["pass", "risk", "manual", "not_applicable"]
AnnotationStatus = Literal["pass", "risk", "not_applicable"]
Severity = Literal["high", "medium", "low"]
Operator = Literal["keyword", "regex"]
Expectation = Literal["present", "absent"]
MatchMode = Literal["any", "all"]
LLMSource = Literal["none", "request", "env"]
LLMStatus = Literal["disabled", "not_needed", "no_key", "ok", "error"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    filename: str | None = Field(default=None, max_length=255)


class EvidenceOut(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    operator: Operator
    keyword: str | None = None


class AIInfoOut(BaseModel):
    mode: Literal["real", "mock", "error"]
    verdict: Literal["pass", "risk", "uncertain"]
    reason: str
    quote: str = ""
    evidence: list[EvidenceOut] = Field(default_factory=list)
    review_required: bool = True
    model: str


class RuleResultOut(BaseModel):
    rule_id: str
    name: str
    description: str
    severity: Severity
    operator: Operator
    status: Status
    matched: bool
    match_count: int = Field(ge=0)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    suggestion: str = ""
    llm_eligible: bool = False
    ai: AIInfoOut | None = None


class LLMInfoOut(BaseModel):
    enabled: bool
    available: bool
    source: LLMSource
    status: LLMStatus
    model: str
    error: str | None = None


class ReviewResponse(BaseModel):
    review_id: str
    created_at: str
    filename: str
    ruleset_version: str
    summary: dict[str, int]
    llm: LLMInfoOut
    results: list[RuleResultOut]


class AnnotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    reviewer: str
    status: AnnotationStatus
    note: str | None = None

    @field_validator("reviewer")
    @classmethod
    def _normalize_reviewer(cls, value: str) -> str:
        reviewer = value.strip()
        if not reviewer:
            raise ValueError("reviewer must not be blank")
        if len(reviewer) > 50:
            raise ValueError("reviewer must be at most 50 characters")
        return reviewer

    @field_validator("note")
    @classmethod
    def _normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        note = value.strip()
        if len(note) > 500:
            raise ValueError("note must be at most 500 characters")
        return note or None


class AnnotationOut(BaseModel):
    rule_id: str
    reviewer: str
    status: AnnotationStatus
    note: str | None = None
    timestamp: str


class AuditEntryOut(BaseModel):
    seq: int = Field(ge=1)
    review_id: str
    rule_id: str
    reviewer: str
    timestamp: str
    old_status: EffectiveStatus
    new_status: AnnotationStatus
    engine_status: Status
    note: str | None = None
    ruleset_version: str


class AnnotationResponse(BaseModel):
    annotation: AnnotationOut
    effective_status: AnnotationStatus
    audit_entry: AuditEntryOut


class ReviewDetailResponse(BaseModel):
    review: dict
    annotations: list[AnnotationOut]
    audit: list[AuditEntryOut]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(min_length=1)
    format: Literal["markdown", "json"] = "markdown"


class ReportResponse(BaseModel):
    filename: str
    mime: str
    content: str


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_configured: bool


class RuleInfoOut(BaseModel):
    id: str
    name: str
    description: str
    severity: Severity
    expect: Expectation
    operator: Operator
    keywords: list[str] | None = None
    match_mode: MatchMode
    pattern: str | None = None
    flags: list[str] = Field(default_factory=list)
    on_match: Status
    on_miss: Status
    suggestion: str
    llm_fallback: bool
    evidence_max: int


class RulesResponse(BaseModel):
    version: str
    rule_count: int
    rules: list[RuleInfoOut]


class SampleInfo(BaseModel):
    id: str
    filename: str
    description: str
    expected: dict[str, int]


class SamplesResponse(BaseModel):
    samples: list[SampleInfo]


class SampleDetailResponse(BaseModel):
    id: str
    filename: str
    text: str
