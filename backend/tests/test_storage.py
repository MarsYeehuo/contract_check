from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.storage import (
    ReviewNotFound,
    ReviewStore,
    RuleNotFound,
    StatusUnchanged,
)

TIMESTAMP = "2026-10-18T08:00:00Z"


def _snapshot(review_id: str, status: str = "risk") -> dict:
    return {
        "review_id": review_id,
        "created_at": TIMESTAMP,
        "filename": "demo.txt",
        "ruleset_version": "sha256:test000000",
        "text": "演示合同文本。",
        "summary": {"total": 1, "pass": 0, "risk": 1, "manual": 0},
        "llm": {
            "enabled": True,
            "available": False,
            "source": "none",
            "status": "no_key",
            "model": "claude-haiku-4-5-20251001",
            "error": None,
        },
        "results": [
            {
                "rule_id": "ip_ownership",
                "name": "知识产权归属",
                "description": "测试",
                "severity": "high",
                "operator": "keyword",
                "status": status,
                "matched": False,
                "match_count": 0,
                "evidence": [],
                "suggestion": "增加条款",
                "llm_eligible": True,
                "ai": None,
            }
        ],
    }


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(tmp_path / "data")


def test_save_and_get_review_snapshot(store: ReviewStore):
    review_id = str(uuid.uuid4())
    snapshot = _snapshot(review_id)

    store.save_review(snapshot)
    loaded = store.get_review(review_id)

    assert loaded == snapshot
    path = store.review_path(review_id)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["review_id"] == review_id
    assert list(path.parent.glob("*.tmp")) == []


def test_get_missing_or_invalid_review(store: ReviewStore):
    with pytest.raises(ReviewNotFound):
        store.get_review(str(uuid.uuid4()))

    with pytest.raises(ReviewNotFound):
        store.get_review("../../etc/passwd")

    with pytest.raises(ReviewNotFound):
        store.get_review("not-a-uuid")


def test_annotation_appends_audit_and_derives_old_status(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id, status="risk"))

    first = store.annotate(
        review_id=review_id,
        rule_id="ip_ownership",
        reviewer="演示审核员",
        new_status="pass",
        note="已补充条款",
        timestamp="2026-10-18T08:01:00Z",
    )

    assert first["seq"] == 1
    assert first["old_status"] == "risk"
    assert first["new_status"] == "pass"
    assert first["engine_status"] == "risk"
    assert first["ruleset_version"] == "sha256:test000000"
    assert first["note"] == "已补充条款"

    second = store.annotate(
        review_id=review_id,
        rule_id="ip_ownership",
        reviewer="复核人",
        new_status="not_applicable",
        note=None,
        timestamp="2026-10-18T08:02:00Z",
    )

    assert second["seq"] == 2
    assert second["old_status"] == "pass"
    assert second["new_status"] == "not_applicable"

    audit = store.read_audit(review_id)
    assert [entry["seq"] for entry in audit] == [1, 2]
    assert len(store.audit_path(review_id).read_text(encoding="utf-8").splitlines()) == 2


def test_annotation_rejects_unchanged_status(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id, status="risk"))

    with pytest.raises(StatusUnchanged):
        store.annotate(
            review_id=review_id,
            rule_id="ip_ownership",
            reviewer="演示审核员",
            new_status="risk",
            note=None,
            timestamp=TIMESTAMP,
        )


def test_annotation_rejects_unknown_rule(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id))

    with pytest.raises(RuleNotFound):
        store.annotate(
            review_id=review_id,
            rule_id="missing_rule",
            reviewer="演示审核员",
            new_status="pass",
            note=None,
            timestamp=TIMESTAMP,
        )


def test_audit_note_newlines_are_json_escaped(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id))

    note = "第一行\n第二行"
    store.annotate(
        review_id=review_id,
        rule_id="ip_ownership",
        reviewer="演示审核员",
        new_status="pass",
        note=note,
        timestamp=TIMESTAMP,
    )

    lines = store.audit_path(review_id).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["note"] == note


def test_get_review_state_returns_latest_annotation_and_audit(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id, status="risk"))
    store.annotate(
        review_id,
        "ip_ownership",
        "演示审核员",
        "pass",
        "第一次",
        "2026-10-18T08:01:00Z",
    )
    store.annotate(
        review_id,
        "ip_ownership",
        "复核人",
        "not_applicable",
        "第二次",
        "2026-10-18T08:02:00Z",
    )

    review, annotations, audit = store.get_review_state(review_id)

    assert review["review_id"] == review_id
    assert len(audit) == 2
    assert annotations == [
        {
            "rule_id": "ip_ownership",
            "reviewer": "复核人",
            "status": "not_applicable",
            "note": "第二次",
            "timestamp": "2026-10-18T08:02:00Z",
        }
    ]


def test_malformed_audit_lines_are_skipped(store: ReviewStore):
    review_id = str(uuid.uuid4())
    store.save_review(_snapshot(review_id))
    store.annotate(
        review_id,
        "ip_ownership",
        "演示审核员",
        "pass",
        None,
        TIMESTAMP,
    )

    path = store.audit_path(review_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write("\n")

    audit = store.read_audit(review_id)
    assert len(audit) == 1
    assert audit[0]["new_status"] == "pass"
