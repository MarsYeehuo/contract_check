from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import RuleEngine, RuleResult
from .llm import judge
from .report import build_json_report, build_markdown_report, report_filename
from .rules import RuleConfigError, RuleStore
from .schemas import (
    AnnotationRequest,
    AnnotationResponse,
    HealthResponse,
    ReportRequest,
    ReportResponse,
    ReviewDetailResponse,
    ReviewRequest,
    ReviewResponse,
    RulesResponse,
    SampleDetailResponse,
    SamplesResponse,
)
from .settings import BACKEND_DIR, Settings
from .storage import (
    ReviewNotFound,
    ReviewStore,
    RuleNotFound,
    StatusUnchanged,
    StorageError,
)

APP_VERSION = "0.1.0"
logger = logging.getLogger(__name__)
MODEL_HEADER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

SAMPLE_CATALOG: tuple[dict, ...] = (
    {
        "id": "sample_pass",
        "filename": "sample_pass.txt",
        "description": "全部规则通过",
        "expected": {"pass": 6, "risk": 0, "manual": 0},
    },
    {
        "id": "sample_risk",
        "filename": "sample_risk.txt",
        "description": "含 2 处风险与 1 处待人工确认",
        "expected": {"pass": 3, "risk": 2, "manual": 1},
    },
)
SAMPLE_BY_ID = {sample["id"]: sample for sample in SAMPLE_CATALOG}


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def sanitize_filename(value: str | None) -> str:
    if not value:
        return "未命名合同.txt"
    name = re.split(r"[\\/]", value.strip())[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return (name or "未命名合同.txt")[:100]


def parse_bool_header(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def find_frontend_dist() -> Path | None:
    candidates: list[Path] = []
    configured = os.getenv("FRONTEND_DIST")
    if configured:
        candidates.append(Path(configured).expanduser().resolve())
    candidates.extend(
        [
            BACKEND_DIR / "frontend" / "dist",
            BACKEND_DIR.parent / "frontend" / "dist",
        ]
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def result_to_dict(result: RuleResult) -> dict:
    return {
        "rule_id": result.rule_id,
        "name": result.name,
        "description": result.description,
        "severity": result.severity,
        "operator": result.operator,
        "status": result.status,
        "matched": result.matched,
        "match_count": result.match_count,
        "evidence": [
            {
                "start": evidence.start,
                "end": evidence.end,
                "text": evidence.text,
                "operator": evidence.operator,
                "keyword": evidence.keyword,
            }
            for evidence in result.evidence
        ],
        "suggestion": result.suggestion,
        "llm_eligible": result.llm_eligible,
        "ai": None,
    }


def resolve_llm_credentials(
    settings: Settings, request: Request
) -> tuple[str | None, str | None, str]:
    request_key = (
        (request.headers.get("X-Anthropic-Api-Key") or "").strip() or None
    )
    if request_key:
        return request_key, "api_key", "request"
    if settings.anthropic_api_key:
        return settings.anthropic_api_key, "api_key", "env"
    if settings.anthropic_auth_token:
        return settings.anthropic_auth_token, "auth_token", "env"
    return None, None, "none"


def requested_model(settings: Settings, request: Request) -> str:
    raw = (request.headers.get("X-Anthropic-Model") or "").strip()
    if raw and MODEL_HEADER_PATTERN.fullmatch(raw):
        return raw
    return settings.anthropic_model


def build_llm_info(
    settings: Settings, request: Request, eligible_count: int
) -> tuple[dict, str | None, str | None]:
    enabled = settings.llm_enabled and parse_bool_header(
        request.headers.get("X-LLM-Enabled"), default=True
    )
    credential, credential_kind, source = resolve_llm_credentials(
        settings, request
    )
    available = enabled and credential is not None

    if not enabled:
        status = "disabled"
    elif eligible_count == 0:
        status = "not_needed"
    elif credential is None:
        status = "no_key"
    else:
        status = "ok"

    info = {
        "enabled": enabled,
        "available": available,
        "source": source,
        "status": status,
        "model": requested_model(settings, request),
        "error": None,
    }
    return info, credential, credential_kind


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    rule_store = RuleStore(settings.rules_path)
    engine = RuleEngine(rule_store)
    review_store = ReviewStore(settings.data_dir)

    app = FastAPI(title="合同初审工具", version=APP_VERSION)
    app.state.settings = settings
    app.state.rule_store = rule_store
    app.state.engine = engine
    app.state.review_store = review_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=[
            "Content-Type",
            "X-Anthropic-Api-Key",
            "X-Anthropic-Model",
            "X-LLM-Enabled",
        ],
    )

    @app.exception_handler(ReviewNotFound)
    async def _review_not_found(
        request: Request, exc: ReviewNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RuleNotFound)
    async def _rule_not_found(
        request: Request, exc: RuleNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(StatusUnchanged)
    async def _status_unchanged(
        request: Request, exc: StatusUnchanged
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(StorageError)
    async def _storage_error(
        request: Request, exc: StorageError
    ) -> JSONResponse:
        logger.exception("storage error")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(RuleConfigError)
    async def _rule_config_error(
        request: Request, exc: RuleConfigError
    ) -> JSONResponse:
        logger.error("rule config error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        return {
            "status": "ok",
            "version": APP_VERSION,
            "llm_configured": bool(
                settings.anthropic_api_key or settings.anthropic_auth_token
            ),
        }

    @app.get("/rules", response_model=RulesResponse)
    def get_rules() -> dict:
        loaded = rule_store.get()
        rules = []
        for compiled in loaded.rules:
            rule = compiled.rule
            rules.append(
                {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "severity": rule.severity,
                    "expect": rule.expect,
                    "operator": rule.operator,
                    "keywords": rule.keywords,
                    "match_mode": rule.match_mode,
                    "pattern": rule.pattern,
                    "flags": rule.flags,
                    "on_match": rule.match_status,
                    "on_miss": rule.miss_status,
                    "suggestion": rule.suggestion,
                    "llm_fallback": rule.llm_fallback,
                    "evidence_max": rule.evidence_max,
                }
            )
        return {
            "version": loaded.version,
            "rule_count": loaded.rule_count,
            "rules": rules,
        }

    @app.get("/samples", response_model=SamplesResponse)
    def get_samples() -> dict:
        return {"samples": [dict(sample) for sample in SAMPLE_CATALOG]}

    @app.get("/samples/{sample_id}", response_model=SampleDetailResponse)
    def get_sample(sample_id: str) -> dict:
        sample = SAMPLE_BY_ID.get(sample_id)
        if sample is None:
            raise HTTPException(status_code=404, detail="样例不存在")
        path = settings.samples_dir / sample["filename"]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"样例文件读取失败: {exc}"
            ) from exc
        return {
            "id": sample_id,
            "filename": sample["filename"],
            "text": text,
        }

    @app.post("/review", response_model=ReviewResponse)
    def review(payload: ReviewRequest, request: Request) -> dict:
        text = payload.text
        if not text.strip():
            raise HTTPException(status_code=400, detail="合同文本不能为空")
        if len(text) > settings.max_text_chars:
            raise HTTPException(
                status_code=413,
                detail=f"合同文本超过 {settings.max_text_chars} 字符",
            )

        started = time.perf_counter()
        evaluation = engine.evaluate(text)
        review_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        filename = sanitize_filename(payload.filename)

        results = [result_to_dict(result) for result in evaluation.results]
        eligible_count = sum(
            1 for result in evaluation.results if result.llm_eligible
        )
        llm, credential, credential_kind = build_llm_info(
            settings, request, eligible_count
        )
        ai_by_rule: dict[str, dict] = {}
        if llm["status"] == "ok":
            if len(text) > settings.llm_max_contract_chars:
                llm["status"] = "error"
                llm["error"] = "contract_too_long"
            else:
                assert credential is not None and credential_kind is not None
                outcome = judge(
                    settings,
                    text,
                    evaluation.results,
                    credential=credential,
                    credential_kind=credential_kind,
                    model=llm["model"],
                )
                if outcome.status == "ok":
                    ai_by_rule = outcome.assessments
                else:
                    llm["status"] = "error"
                    llm["error"] = outcome.error
                logger.info(
                    "llm status=%s model=%s duration_ms=%.1f",
                    outcome.status,
                    outcome.model,
                    outcome.duration_ms,
                )

        for item in results:
            ai = ai_by_rule.get(item["rule_id"])
            if ai is not None:
                item["ai"] = ai

        snapshot = {
            "review_id": review_id,
            "created_at": created_at,
            "filename": filename,
            "ruleset_version": evaluation.ruleset_version,
            "text": text,
            "summary": dict(evaluation.summary),
            "llm": llm,
            "results": results,
        }
        review_store.save_review(snapshot)

        logger.info(
            "review created id=%s ruleset=%s chars=%d duration_ms=%.1f",
            review_id,
            evaluation.ruleset_version,
            len(text),
            (time.perf_counter() - started) * 1000,
        )
        return {
            "review_id": review_id,
            "created_at": created_at,
            "filename": filename,
            "ruleset_version": evaluation.ruleset_version,
            "summary": dict(evaluation.summary),
            "llm": llm,
            "results": results,
        }

    @app.post("/annotations", response_model=AnnotationResponse)
    def annotate(payload: AnnotationRequest) -> dict:
        timestamp = utc_now_iso()
        entry = review_store.annotate(
            review_id=payload.review_id,
            rule_id=payload.rule_id,
            reviewer=payload.reviewer,
            new_status=payload.status,
            note=payload.note,
            timestamp=timestamp,
        )
        logger.info(
            "annotation review=%s rule=%s reviewer=%s %s->%s",
            entry["review_id"],
            entry["rule_id"],
            entry["reviewer"],
            entry["old_status"],
            entry["new_status"],
        )
        return {
            "annotation": {
                "rule_id": entry["rule_id"],
                "reviewer": entry["reviewer"],
                "status": entry["new_status"],
                "note": entry.get("note"),
                "timestamp": entry["timestamp"],
            },
            "effective_status": entry["new_status"],
            "audit_entry": entry,
        }

    @app.get("/reviews/{review_id}", response_model=ReviewDetailResponse)
    def get_review(review_id: str) -> dict:
        review_document, annotations, audit = review_store.get_review_state(
            review_id
        )
        return {
            "review": review_document,
            "annotations": annotations,
            "audit": audit,
        }

    @app.post("/report", response_model=ReportResponse)
    def create_report(payload: ReportRequest) -> dict:
        review_document, _annotations, audit = review_store.get_review_state(
            payload.review_id
        )
        generated_at = utc_now_iso()
        filename = report_filename(
            review_document, payload.format, generated_at
        )

        if payload.format == "json":
            document = build_json_report(review_document, audit, generated_at)
            return {
                "filename": filename,
                "mime": "application/json; charset=utf-8",
                "content": json.dumps(document, ensure_ascii=False, indent=2),
            }

        return {
            "filename": filename,
            "mime": "text/markdown; charset=utf-8",
            "content": build_markdown_report(
                review_document, audit, generated_at
            ),
        }

    frontend_dist = find_frontend_dist()
    if frontend_dist is not None:
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="frontend",
        )

    return app


app = create_app()
