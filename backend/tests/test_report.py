from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.report import DISCLAIMER
from app.settings import BACKEND_DIR, Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        rules_path=BACKEND_DIR / "rules" / "review_rules.yaml",
        samples_dir=BACKEND_DIR / "samples",
        max_text_chars=200_000,
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


def _create_review(
    client: TestClient, settings: Settings, filename: str, name: str | None = None
) -> dict:
    response = client.post(
        "/review",
        json={
            "text": (settings.samples_dir / filename).read_text(encoding="utf-8"),
            "filename": name or filename,
        },
    )
    assert response.status_code == 200
    return response.json()


def _annotate(
    client: TestClient,
    review_id: str,
    rule_id: str,
    status: str,
    reviewer: str = "演示审核员",
    note: str | None = None,
) -> None:
    response = client.post(
        "/annotations",
        json={
            "review_id": review_id,
            "rule_id": rule_id,
            "reviewer": reviewer,
            "status": status,
            "note": note,
        },
    )
    assert response.status_code == 200


def _report(client: TestClient, review_id: str, fmt: str | None = None) -> dict:
    payload: dict = {"review_id": review_id}
    if fmt is not None:
        payload["format"] = fmt
    response = client.post("/report", json=payload)
    assert response.status_code == 200
    return response.json()


def test_markdown_report_contains_summary_rules_and_audit(
    client: TestClient, settings: Settings
):
    review = _create_review(client, settings, "sample_risk.txt")
    _annotate(
        client,
        review["review_id"],
        "ip_ownership",
        "pass",
        note="已补充知识产权条款",
    )

    body = _report(client, review["review_id"])

    assert body["mime"] == "text/markdown; charset=utf-8"
    assert body["filename"].startswith("审查报告_sample_risk_")
    assert body["filename"].endswith(".md")

    content = body["content"]
    assert content.startswith("# 合同初审报告")
    assert "- 合同文件：sample_risk.txt" in content
    assert "- 规则版本：sha256:" in content
    assert "- 审核人：演示审核员（来自人工标注记录）" in content
    assert "- 总体结论：存在风险" in content
    assert "- 规则总数：6" in content
    assert "- 通过：4" in content
    assert "- 风险：1" in content
    assert "- 需人工确认：1" in content
    assert "- 不适用：0" in content
    assert "- 人工覆盖：1 条" in content
    assert "### 1. 违约金比例上限（高）" in content
    assert "### 2. 知识产权归属（高）" in content
    assert "- 引擎初判：风险" in content
    assert "- 最终结论：通过" in content
    assert "- 人工备注：已补充知识产权条款" in content
    assert "> 违约金为合同总金额的 50%（原文偏移" in content
    assert "| 演示审核员 | 知识产权归属 | risk | pass | 已补充知识产权条款 |" in content
    assert DISCLAIMER in content
    assert "- AI 建议（需人工复核）" not in content


def test_json_report_structure(client: TestClient, settings: Settings):
    review = _create_review(client, settings, "sample_risk.txt")
    _annotate(
        client,
        review["review_id"],
        "ip_ownership",
        "pass",
        note="已补充知识产权条款",
    )

    body = _report(client, review["review_id"], "json")

    assert body["mime"] == "application/json; charset=utf-8"
    assert body["filename"].endswith(".json")

    document = json.loads(body["content"])
    assert document["review_id"] == review["review_id"]
    assert document["filename"] == "sample_risk.txt"
    assert document["created_at"] == review["created_at"]
    assert document["generated_at"].endswith("Z")
    assert document["ruleset"] == {
        "version": review["ruleset_version"],
        "rule_count": 6,
    }
    assert document["summary"] == {
        "total": 6,
        "pass": 4,
        "risk": 1,
        "manual": 1,
        "not_applicable": 0,
        "overridden": 1,
        "conclusion": "存在风险",
    }

    rules = {rule["rule_id"]: rule for rule in document["rules"]}
    ip_rule = rules["ip_ownership"]
    assert ip_rule["engine_status"] == "risk"
    assert ip_rule["final_status"] == "pass"
    assert ip_rule["annotation"] == {
        "reviewer": "演示审核员",
        "timestamp": document["audit"][0]["timestamp"],
        "note": "已补充知识产权条款",
    }
    assert ip_rule["evidence"] == []
    assert ip_rule["ai"] is None

    assert len(document["audit"]) == 1
    audit_entry = document["audit"][0]
    assert audit_entry["seq"] == 1
    assert audit_entry["old_status"] == "risk"
    assert audit_entry["new_status"] == "pass"
    assert document["disclaimer"] == DISCLAIMER


def test_not_applicable_does_not_block_conclusion(
    client: TestClient, settings: Settings
):
    review = _create_review(client, settings, "sample_pass.txt")
    _annotate(
        client,
        review["review_id"],
        "ip_ownership",
        "not_applicable",
        note="本项目不涉及知识产权",
    )

    document = json.loads(_report(client, review["review_id"], "json")["content"])

    assert document["summary"] == {
        "total": 6,
        "pass": 5,
        "risk": 0,
        "manual": 0,
        "not_applicable": 1,
        "overridden": 1,
        "conclusion": "未发现风险",
    }


def test_manual_items_drive_conclusion(client: TestClient, settings: Settings):
    review = _create_review(client, settings, "sample_risk.txt")
    _annotate(client, review["review_id"], "penalty_ratio", "pass")
    _annotate(client, review["review_id"], "ip_ownership", "pass")

    document = json.loads(_report(client, review["review_id"], "json")["content"])

    assert document["summary"]["pass"] == 5
    assert document["summary"]["risk"] == 0
    assert document["summary"]["manual"] == 1
    assert document["summary"]["overridden"] == 2
    assert document["summary"]["conclusion"] == "存在待人工确认项"


def test_report_without_annotations(client: TestClient, settings: Settings):
    review = _create_review(client, settings, "sample_risk.txt")

    markdown = _report(client, review["review_id"])["content"]
    assert "无人工修改记录。" in markdown
    assert "- 人工覆盖：0 条" in markdown

    document = json.loads(_report(client, review["review_id"], "json")["content"])
    assert document["audit"] == []
    assert document["summary"]["overridden"] == 0
    assert all(
        rule["annotation"] is None and rule["final_status"] == rule["engine_status"]
        for rule in document["rules"]
    )


def test_report_escapes_user_content(client: TestClient, settings: Settings):
    review = _create_review(
        client,
        settings,
        "sample_risk.txt",
        name="../../合同<v1>.txt",
    )
    _annotate(
        client,
        review["review_id"],
        "ip_ownership",
        "pass",
        reviewer="<b>审核</b>",
        note="含 | 竖线\n第二行 <script>alert(1)</script> `code`",
    )

    body = _report(client, review["review_id"])
    content = body["content"]

    assert "<script>" not in content
    assert "&lt;script&gt;" in content
    assert "&lt;b&gt;审核&lt;/b&gt;" in content
    assert "含 \\| 竖线" in content
    assert "第二行 &lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "\\`code\\`" in content
    assert "<br>" in content

    for illegal in '<>:"/\\|?*':
        assert illegal not in body["filename"]
    assert body["filename"].startswith("审查报告_合同_v1__")


def test_report_errors(client: TestClient, settings: Settings):
    review = _create_review(client, settings, "sample_risk.txt")

    missing = client.post("/report", json={"review_id": str(uuid.uuid4())})
    assert missing.status_code == 404

    invalid_id = client.post("/report", json={"review_id": "../../etc/passwd"})
    assert invalid_id.status_code == 404

    bad_format = client.post(
        "/report", json={"review_id": review["review_id"], "format": "pdf"}
    )
    assert bad_format.status_code == 422

    extra_field = client.post(
        "/report",
        json={"review_id": review["review_id"], "format": "json", "foo": 1},
    )
    assert extra_field.status_code == 422

    missing_id = client.post("/report", json={"format": "json"})
    assert missing_id.status_code == 422
