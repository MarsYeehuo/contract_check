from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app import llm as llm_module
from app.engine import RuleEngine
from app.llm import (
    build_system_prompt,
    build_user_prompt,
    judge,
    parse_assessments,
)
from app.rules import RuleStore
from app.settings import BACKEND_DIR, Settings

RISK_SAMPLE = "sample_risk.txt"


def _settings(**overrides) -> Settings:
    values = {
        "data_dir": Path("data-test"),
        "rules_path": BACKEND_DIR / "rules" / "review_rules.yaml",
        "samples_dir": BACKEND_DIR / "samples",
        "max_text_chars": 200_000,
        "llm_enabled": True,
        "anthropic_api_key": "env-key",
        "anthropic_model": "test-model",
        "llm_timeout_seconds": 20.0,
        "llm_max_contract_chars": 50_000,
        "cors_origins": ("http://localhost:5173",),
    }
    values.update(overrides)
    return Settings(**values)


def _sample_text() -> str:
    return (BACKEND_DIR / "samples" / RISK_SAMPLE).read_text(encoding="utf-8")


def _results():
    engine = RuleEngine(RuleStore(BACKEND_DIR / "rules" / "review_rules.yaml"))
    return engine.evaluate(_sample_text()).results


def _install_fake_client(monkeypatch, *, payload=None, exc=None) -> dict:
    captured: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["request"] = kwargs
            if exc is not None:
                raise exc
            return SimpleNamespace(
                content=[SimpleNamespace(text=payload)]
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(llm_module.anthropic, "Anthropic", FakeAnthropic)
    return captured


def test_prompts_include_rules_and_contract():
    results = _results()
    system = build_system_prompt(results)
    user = build_user_prompt(_sample_text(), [r for r in results if r.llm_eligible])

    assert "ip_ownership" in system
    assert "只输出 JSON" in system
    assert "忽略" in system
    assert "ip_ownership" in user
    assert "<contract>" in user and "</contract>" in user
    assert "乙方" in user


def test_parse_assessments_strips_fence_and_computes_offsets():
    text = "甲方😀乙方。技术成果归甲方所有。"
    raw = (
        "```json\n"
        + json.dumps(
            {
                "assessments": [
                    {
                        "rule_id": "ip_ownership",
                        "verdict": "pass",
                        "reason": "约定了技术成果归属。",
                        "quote": "技术成果",
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n```"
    )

    assessments = parse_assessments(raw, text, {"ip_ownership"}, "test-model")
    ai = assessments["ip_ownership"]
    assert ai["mode"] == "real"
    assert ai["verdict"] == "pass"
    assert ai["review_required"] is True
    assert ai["quote"] == "技术成果"
    assert ai["evidence"] == [
        {
            "start": text.find("技术成果"),
            "end": text.find("技术成果") + len("技术成果"),
            "text": "技术成果",
            "operator": "keyword",
            "keyword": None,
        }
    ]


def test_parse_assessments_ignores_unknown_and_invalid_entries():
    raw = json.dumps(
        {
            "assessments": [
                {
                    "rule_id": "ip_ownership",
                    "verdict": "uncertain",
                    "reason": "未找到明确约定。",
                    "quote": "",
                },
                {
                    "rule_id": "unknown_rule",
                    "verdict": "pass",
                    "reason": "x",
                    "quote": "",
                },
                {
                    "rule_id": "payment_term",
                    "verdict": "maybe",
                    "reason": "x",
                    "quote": "",
                },
            ]
        },
        ensure_ascii=False,
    )
    assessments = parse_assessments(
        raw, "合同文本", {"ip_ownership", "payment_term"}, "m"
    )
    assert list(assessments) == ["ip_ownership"]
    assert assessments["ip_ownership"]["evidence"] == []


def test_parse_assessments_rejects_empty_result():
    with pytest.raises(ValueError):
        parse_assessments(
            json.dumps({"assessments": []}),
            "合同文本",
            {"ip_ownership"},
            "m",
        )


def test_parse_assessments_truncates_reason_and_quote():
    text = "x" * 600
    raw = json.dumps(
        {
            "assessments": [
                {
                    "rule_id": "ip_ownership",
                    "verdict": "risk",
                    "reason": "r" * 400,
                    "quote": "x" * 600,
                }
            ]
        }
    )
    assessments = parse_assessments(raw, text, {"ip_ownership"}, "m")
    ai = assessments["ip_ownership"]
    assert len(ai["reason"]) == 300
    assert len(ai["quote"]) == 500
    assert ai["evidence"][0]["end"] == 500


def test_parse_assessments_quote_not_found_yields_empty_evidence():
    raw = json.dumps(
        {
            "assessments": [
                {
                    "rule_id": "ip_ownership",
                    "verdict": "pass",
                    "reason": "x",
                    "quote": "不存在的片段",
                }
            ]
        }
    )
    assessments = parse_assessments(
        raw, "合同文本", {"ip_ownership"}, "m"
    )
    assert assessments["ip_ownership"]["evidence"] == []


def test_judge_success_uses_auth_token_and_base_url(monkeypatch):
    captured = _install_fake_client(
        monkeypatch,
        payload=json.dumps(
            {
                "assessments": [
                    {
                        "rule_id": "ip_ownership",
                        "verdict": "uncertain",
                        "reason": "未发现明确约定。",
                        "quote": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )
    settings = _settings(
        anthropic_api_key=None,
        anthropic_auth_token="secret-token",
        anthropic_base_url="https://api.example.test/anthropic",
    )

    outcome = judge(
        settings,
        _sample_text(),
        _results(),
        credential="secret-token",
        credential_kind="auth_token",
        model="deepseek-flash",
    )

    assert outcome.status == "ok"
    assert outcome.error is None
    assert outcome.model == "deepseek-flash"
    assert set(outcome.assessments) == {"ip_ownership"}

    client_kwargs = captured["client"]
    assert client_kwargs["auth_token"] == "secret-token"
    assert "api_key" not in client_kwargs
    assert (
        client_kwargs["base_url"]
        == "https://api.example.test/anthropic"
    )
    request = captured["request"]
    assert request["model"] == "deepseek-flash"
    assert request["temperature"] == 0
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_judge_timeout_degrades(monkeypatch):
    exc = anthropic.APITimeoutError(
        request=httpx.Request("POST", "https://api.example.test")
    )
    _install_fake_client(monkeypatch, exc=exc)

    outcome = judge(
        _settings(),
        _sample_text(),
        _results(),
        credential="key",
        credential_kind="api_key",
    )

    assert outcome.status == "error"
    assert outcome.error == "timeout"
    assert outcome.assessments == {}


def test_judge_parse_error_degrades(monkeypatch):
    _install_fake_client(monkeypatch, payload="这不是 JSON")

    outcome = judge(
        _settings(),
        _sample_text(),
        _results(),
        credential="key",
        credential_kind="api_key",
    )

    assert outcome.status == "error"
    assert outcome.error == "parse_error"
    assert outcome.assessments == {}
