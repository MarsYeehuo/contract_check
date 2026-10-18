from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import BACKEND_DIR, Settings

RISK_SAMPLE = "sample_risk.txt"
PASS_SAMPLE = "sample_pass.txt"


def _settings(tmp_path: Path, max_text_chars: int = 200_000) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        rules_path=BACKEND_DIR / "rules" / "review_rules.yaml",
        samples_dir=BACKEND_DIR / "samples",
        max_text_chars=max_text_chars,
        llm_enabled=True,
        anthropic_api_key=None,
        anthropic_model="claude-haiku-4-5-20251001",
        llm_timeout_seconds=20.0,
        llm_max_contract_chars=50_000,
        cors_origins=("http://localhost:5173",),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _sample_text(settings: Settings, filename: str) -> str:
    return (settings.samples_dir / filename).read_text(encoding="utf-8")


def _create_review(
    client: TestClient, settings: Settings, filename: str = RISK_SAMPLE
) -> dict:
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, filename), "filename": filename},
    )
    assert response.status_code == 200
    return response.json()


def _annotate(client: TestClient, review_id: str, **overrides) -> dict:
    payload = {
        "review_id": review_id,
        "rule_id": "ip_ownership",
        "reviewer": "演示审核员",
        "status": "pass",
        "note": None,
    }
    payload.update(overrides)
    response = client.post("/annotations", json=payload)
    return {"status_code": response.status_code, "body": response.json()}


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["llm_configured"] is False


def test_rules_catalog(client: TestClient):
    response = client.get("/rules")
    assert response.status_code == 200
    body = response.json()

    assert body["rule_count"] == 6
    assert body["version"].startswith("sha256:")
    by_id = {rule["id"]: rule for rule in body["rules"]}
    assert set(by_id) == {
        "penalty_ratio",
        "ip_ownership",
        "payment_term",
        "dispute_resolution",
        "confidentiality",
        "auto_renewal",
    }
    assert by_id["penalty_ratio"]["on_match"] == "risk"
    assert by_id["penalty_ratio"]["on_miss"] == "pass"
    assert by_id["ip_ownership"]["on_match"] == "pass"
    assert by_id["ip_ownership"]["on_miss"] == "risk"
    assert by_id["auto_renewal"]["on_match"] == "manual"
    assert by_id["auto_renewal"]["on_miss"] == "pass"


def test_samples_catalog_and_detail(client: TestClient):
    response = client.get("/samples")
    assert response.status_code == 200
    samples = response.json()["samples"]
    assert [sample["id"] for sample in samples] == ["sample_pass", "sample_risk"]
    assert samples[0]["expected"] == {"pass": 6, "risk": 0, "manual": 0}
    assert samples[1]["expected"] == {"pass": 3, "risk": 2, "manual": 1}

    detail = client.get("/samples/sample_risk")
    assert detail.status_code == 200
    body = detail.json()
    assert body["filename"] == RISK_SAMPLE
    assert body["text"].strip()

    assert client.get("/samples/unknown").status_code == 404


def test_review_all_pass_sample(client: TestClient, settings: Settings):
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, PASS_SAMPLE), "filename": PASS_SAMPLE},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["summary"] == {"total": 6, "pass": 6, "risk": 0, "manual": 0}
    assert body["filename"] == PASS_SAMPLE
    assert body["llm"]["status"] == "not_needed"
    assert body["llm"]["available"] is False
    assert body["llm"]["source"] == "none"
    assert all(result["status"] == "pass" for result in body["results"])

    snapshot_path = settings.data_dir / "reviews" / f"{body['review_id']}.json"
    assert snapshot_path.is_file()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["review_id"] == body["review_id"]
    assert snapshot["summary"] == body["summary"]


def test_review_risk_sample(client: TestClient, settings: Settings):
    body = _create_review(client, settings, RISK_SAMPLE)

    assert body["summary"] == {"total": 6, "pass": 3, "risk": 2, "manual": 1}
    statuses = {result["rule_id"]: result["status"] for result in body["results"]}
    assert statuses["penalty_ratio"] == "risk"
    assert statuses["ip_ownership"] == "risk"
    assert statuses["auto_renewal"] == "manual"
    assert body["llm"]["status"] == "no_key"
    assert body["llm"]["available"] is False
    assert body["llm"]["error"] is None


def test_review_evidence_offsets_point_into_source(
    client: TestClient, settings: Settings
):
    text = _sample_text(settings, RISK_SAMPLE)
    body = _create_review(client, settings, RISK_SAMPLE)

    found = 0
    for result in body["results"]:
        for evidence in result["evidence"]:
            assert text[evidence["start"] : evidence["end"]] == evidence["text"]
            found += 1
    assert found > 0
    assert any(
        result["rule_id"] == "penalty_ratio" and result["evidence"]
        for result in body["results"]
    )


def test_review_rejects_blank_and_oversized_text(
    client: TestClient, tmp_path: Path
):
    blank = client.post("/review", json={"text": "   \n\t "})
    assert blank.status_code == 400

    small_settings = _settings(tmp_path / "small", max_text_chars=10)
    with TestClient(create_app(small_settings)) as small_client:
        oversized = small_client.post("/review", json={"text": "合同" * 6})
    assert oversized.status_code == 413


def test_review_request_validation(client: TestClient):
    missing_text = client.post("/review", json={"filename": "a.txt"})
    assert missing_text.status_code == 422

    extra_field = client.post("/review", json={"text": "正文", "foo": 1})
    assert extra_field.status_code == 422


def test_review_sanitizes_filename(client: TestClient):
    response = client.post("/review", json={"text": "合同正文", "filename": "../../etc/passwd"})
    assert response.status_code == 200
    assert response.json()["filename"] == "passwd"


def test_annotation_lifecycle(client: TestClient, settings: Settings):
    review = _create_review(client, settings, RISK_SAMPLE)
    review_id = review["review_id"]

    first = _annotate(
        client,
        review_id,
        status="pass",
        note="已补充知识产权条款",
    )
    assert first["status_code"] == 200
    body = first["body"]
    assert body["annotation"]["rule_id"] == "ip_ownership"
    assert body["annotation"]["status"] == "pass"
    assert body["effective_status"] == "pass"
    assert body["audit_entry"]["seq"] == 1
    assert body["audit_entry"]["old_status"] == "risk"
    assert body["audit_entry"]["new_status"] == "pass"
    assert body["audit_entry"]["engine_status"] == "risk"
    assert body["audit_entry"]["ruleset_version"] == review["ruleset_version"]

    second = _annotate(client, review_id, status="not_applicable", reviewer="复核人")
    assert second["status_code"] == 200
    assert second["body"]["audit_entry"]["seq"] == 2
    assert second["body"]["audit_entry"]["old_status"] == "pass"
    assert second["body"]["audit_entry"]["new_status"] == "not_applicable"
    assert second["body"]["annotation"]["reviewer"] == "复核人"

    detail = client.get(f"/reviews/{review_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["review"]["review_id"] == review_id
    assert len(detail_body["audit"]) == 2
    assert detail_body["annotations"] == [
        {
            "rule_id": "ip_ownership",
            "reviewer": "复核人",
            "status": "not_applicable",
            "note": None,
            "timestamp": detail_body["audit"][1]["timestamp"],
        }
    ]


def test_annotation_rejections(client: TestClient, settings: Settings):
    review_id = _create_review(client, settings, RISK_SAMPLE)["review_id"]

    unchanged = _annotate(client, review_id, status="risk")
    assert unchanged["status_code"] == 409

    unknown_rule = _annotate(client, review_id, rule_id="missing_rule")
    assert unknown_rule["status_code"] == 404

    missing_review = _annotate(client, str(uuid.uuid4()), status="pass")
    assert missing_review["status_code"] == 404

    bad_review_id = _annotate(client, "../../etc/passwd", status="pass")
    assert bad_review_id["status_code"] == 404

    bad_status = _annotate(client, review_id, status="manual")
    assert bad_status["status_code"] == 422

    blank_reviewer = _annotate(client, review_id, reviewer="   ")
    assert blank_reviewer["status_code"] == 422

    long_note = _annotate(client, review_id, note="字" * 501)
    assert long_note["status_code"] == 422


def test_annotation_note_with_newline_is_single_audit_line(
    client: TestClient, settings: Settings
):
    review_id = _create_review(client, settings, RISK_SAMPLE)["review_id"]
    response = _annotate(client, review_id, status="pass", note="第一行\n第二行")
    assert response["status_code"] == 200

    audit_path = settings.data_dir / "audit" / f"{review_id}.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["note"] == "第一行\n第二行"


def test_get_missing_review_returns_404(client: TestClient):
    response = client.get(f"/reviews/{uuid.uuid4()}")
    assert response.status_code == 404

    invalid = client.get("/reviews/not-a-uuid")
    assert invalid.status_code == 404


def test_llm_header_can_disable_fallback(client: TestClient, settings: Settings):
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={"X-LLM-Enabled": "false"},
    )
    assert response.status_code == 200
    assert response.json()["llm"]["status"] == "disabled"
    assert response.json()["llm"]["enabled"] is False


def _fake_judge(outcome):
    def fake(settings, text, results, **kwargs):
        return outcome

    return fake


def test_request_key_is_used_but_never_echoed(
    client: TestClient, settings: Settings, monkeypatch
):
    import app.main as main_module
    from app.llm import LlmOutcome

    monkeypatch.setattr(
        main_module,
        "judge",
        _fake_judge(
            LlmOutcome(
                status="error", error="bad_request", model="test-model"
            )
        ),
    )
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={"X-Anthropic-Api-Key": "sk-ant-test-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["source"] == "request"
    assert body["llm"]["available"] is True
    assert body["llm"]["status"] == "error"
    assert body["llm"]["error"] == "bad_request"
    assert "sk-ant-test-secret" not in response.text

    snapshot = (
        settings.data_dir / "reviews" / f"{body['review_id']}.json"
    ).read_text(encoding="utf-8")
    assert "sk-ant-test-secret" not in snapshot
    assert all(result["ai"] is None for result in body["results"])


def test_llm_success_attaches_ai_without_changing_status(
    client: TestClient, settings: Settings, monkeypatch
):
    import app.main as main_module
    from app.llm import LlmOutcome

    ai = {
        "mode": "real",
        "verdict": "pass",
        "reason": "合同提到了技术成果归属。",
        "quote": "技术成果",
        "evidence": [
            {
                "start": 0,
                "end": 4,
                "text": "技术成果",
                "operator": "keyword",
                "keyword": None,
            }
        ],
        "review_required": True,
        "model": "test-model",
    }

    def fake(settings, text, results, **kwargs):
        return LlmOutcome(
            status="ok",
            error=None,
            model="test-model",
            assessments={"ip_ownership": ai},
        )

    monkeypatch.setattr(main_module, "judge", fake)
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={"X-Anthropic-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["status"] == "ok"
    assert body["llm"]["error"] is None
    ip_result = next(
        item for item in body["results"] if item["rule_id"] == "ip_ownership"
    )
    assert ip_result["status"] == "risk"
    assert ip_result["ai"]["mode"] == "real"
    assert ip_result["ai"]["review_required"] is True

    snapshot = json.loads(
        (
            settings.data_dir / "reviews" / f"{body['review_id']}.json"
        ).read_text(encoding="utf-8")
    )
    snapshot_ip = next(
        item
        for item in snapshot["results"]
        if item["rule_id"] == "ip_ownership"
    )
    assert snapshot_ip["ai"]["mode"] == "real"
    assert "test-key" not in json.dumps(snapshot)


def test_llm_failure_degrades_to_error(
    client: TestClient, settings: Settings, monkeypatch
):
    import app.main as main_module
    from app.llm import LlmOutcome

    monkeypatch.setattr(
        main_module,
        "judge",
        _fake_judge(
            LlmOutcome(
                status="error", error="timeout", model="test-model"
            )
        ),
    )
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={"X-Anthropic-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["status"] == "error"
    assert body["llm"]["error"] == "timeout"
    assert all(result["ai"] is None for result in body["results"])


def test_llm_skipped_when_contract_too_long(
    client: TestClient, tmp_path: Path, monkeypatch
):
    import app.main as main_module
    from app.settings import Settings

    settings = Settings(
        data_dir=tmp_path / "data-long",
        rules_path=BACKEND_DIR / "rules" / "review_rules.yaml",
        samples_dir=BACKEND_DIR / "samples",
        max_text_chars=200_000,
        llm_enabled=True,
        anthropic_api_key="env-key",
        anthropic_model="test-model",
        llm_timeout_seconds=20.0,
        llm_max_contract_chars=10,
        cors_origins=("http://localhost:5173",),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("judge must not be called")

    monkeypatch.setattr(main_module, "judge", fail_if_called)
    text = (settings.samples_dir / RISK_SAMPLE).read_text(encoding="utf-8")
    with TestClient(create_app(settings)) as long_client:
        response = long_client.post("/review", json={"text": text})
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["source"] == "env"
    assert body["llm"]["status"] == "error"
    assert body["llm"]["error"] == "contract_too_long"


def test_env_auth_token_is_supported(tmp_path: Path, monkeypatch):
    import app.main as main_module
    from app.llm import LlmOutcome
    from app.settings import Settings

    settings = Settings(
        data_dir=tmp_path / "data-token",
        rules_path=BACKEND_DIR / "rules" / "review_rules.yaml",
        samples_dir=BACKEND_DIR / "samples",
        max_text_chars=200_000,
        llm_enabled=True,
        anthropic_api_key=None,
        anthropic_model="deepseek-flash",
        llm_timeout_seconds=20.0,
        llm_max_contract_chars=50_000,
        cors_origins=("http://localhost:5173",),
        anthropic_base_url="https://api.example.test/anthropic",
        anthropic_auth_token="env-auth-token",
    )

    def fake(settings, text, results, **kwargs):
        return LlmOutcome(
            status="error", error="network_error", model=kwargs["model"]
        )

    monkeypatch.setattr(main_module, "judge", fake)
    text = (settings.samples_dir / RISK_SAMPLE).read_text(encoding="utf-8")
    with TestClient(create_app(settings)) as token_client:
        health = token_client.get("/health")
        assert health.json()["llm_configured"] is True
        response = token_client.post("/review", json={"text": text})
    body = response.json()
    assert body["llm"]["source"] == "env"
    assert body["llm"]["available"] is True
    assert body["llm"]["status"] == "error"
    assert "env-auth-token" not in response.text


def test_model_header_overrides_model(
    client: TestClient, settings: Settings, monkeypatch
):
    import app.main as main_module
    from app.llm import LlmOutcome

    captured: dict = {}

    def fake(settings, text, results, **kwargs):
        captured.update(kwargs)
        captured["model"] = kwargs.get("model")
        return LlmOutcome(
            status="error", error="network_error", model=kwargs["model"]
        )

    monkeypatch.setattr(main_module, "judge", fake)
    response = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={
            "X-Anthropic-Api-Key": "test-key",
            "X-Anthropic-Model": "deepseek-flash",
        },
    )
    assert response.status_code == 200
    assert response.json()["llm"]["model"] == "deepseek-flash"
    assert captured["model"] == "deepseek-flash"

    invalid = client.post(
        "/review",
        json={"text": _sample_text(settings, RISK_SAMPLE)},
        headers={
            "X-Anthropic-Api-Key": "test-key",
            "X-Anthropic-Model": "bad model!",
        },
    )
    assert invalid.status_code == 200
    assert invalid.json()["llm"]["model"] == settings.anthropic_model
