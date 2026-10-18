from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_NEW_STATUSES = {"pass", "risk", "not_applicable"}


class ReviewNotFound(Exception):
    def __init__(self, review_id: str):
        super().__init__(f"审查记录不存在: {review_id}")
        self.review_id = review_id


class RuleNotFound(Exception):
    def __init__(self, rule_id: str):
        super().__init__(f"规则不存在: {rule_id}")
        self.rule_id = rule_id


class StatusUnchanged(Exception):
    def __init__(self, status: str):
        super().__init__(f"状态未发生变化: {status}")
        self.status = status


class StorageError(Exception):
    pass


class ReviewStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.reviews_dir = self.data_dir / "reviews"
        self.audit_dir = self.data_dir / "audit"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def _canonical_id(review_id: str) -> str:
        try:
            return str(uuid.UUID(str(review_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ReviewNotFound(str(review_id)) from exc

    def review_path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{self._canonical_id(review_id)}.json"

    def audit_path(self, review_id: str) -> Path:
        return self.audit_dir / f"{self._canonical_id(review_id)}.jsonl"

    def save_review(self, snapshot: dict[str, Any]) -> None:
        canonical = self._canonical_id(str(snapshot.get("review_id", "")))
        path = self.reviews_dir / f"{canonical}.json"
        try:
            self._write_json_atomic(path, snapshot)
        except OSError as exc:
            raise StorageError(f"无法保存审查记录 {canonical}: {exc}") from exc

    def _write_json_atomic(self, path: Path, document: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def _read_review_unlocked(self, canonical: str) -> dict[str, Any]:
        path = self.reviews_dir / f"{canonical}.json"
        try:
            with path.open(encoding="utf-8") as handle:
                document = json.load(handle)
        except FileNotFoundError as exc:
            raise ReviewNotFound(canonical) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"无法读取审查记录 {canonical}: {exc}") from exc
        if not isinstance(document, dict):
            raise StorageError(f"审查记录格式错误: {canonical}")
        return document

    def get_review(self, review_id: str) -> dict[str, Any]:
        return self._read_review_unlocked(self._canonical_id(review_id))

    def _read_audit_unlocked(self, canonical: str) -> list[dict[str, Any]]:
        path = self.audit_dir / f"{canonical}.jsonl"
        if not path.exists():
            return []

        entries: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        entry = json.loads(stripped)
                    except json.JSONDecodeError:
                        logger.warning(
                            "跳过损坏的审计行 %s:%s", path, line_number
                        )
                        continue
                    if isinstance(entry, dict):
                        entries.append(entry)
                    else:
                        logger.warning(
                            "跳过非对象审计行 %s:%s", path, line_number
                        )
        except OSError as exc:
            raise StorageError(f"无法读取审计记录 {canonical}: {exc}") from exc

        entries.sort(key=lambda entry: int(entry.get("seq", 0)))
        return entries

    def read_audit(self, review_id: str) -> list[dict[str, Any]]:
        canonical = self._canonical_id(review_id)
        with self._lock:
            return self._read_audit_unlocked(canonical)

    def annotate(
        self,
        review_id: str,
        rule_id: str,
        reviewer: str,
        new_status: str,
        note: str | None,
        timestamp: str,
    ) -> dict[str, Any]:
        canonical = self._canonical_id(review_id)
        if new_status not in ALLOWED_NEW_STATUSES:
            raise ValueError(f"invalid annotation status: {new_status}")

        with self._lock:
            review = self._read_review_unlocked(canonical)
            result = next(
                (
                    item
                    for item in review.get("results", [])
                    if item.get("rule_id") == rule_id
                ),
                None,
            )
            if result is None:
                raise RuleNotFound(rule_id)

            audit = self._read_audit_unlocked(canonical)
            engine_status = result.get("status")
            old_status = engine_status
            for entry in audit:
                if entry.get("rule_id") == rule_id and entry.get("new_status"):
                    old_status = entry["new_status"]

            if new_status == old_status:
                raise StatusUnchanged(new_status)

            seq = max((int(entry.get("seq", 0)) for entry in audit), default=0) + 1
            entry = {
                "seq": seq,
                "review_id": canonical,
                "rule_id": rule_id,
                "reviewer": reviewer,
                "timestamp": timestamp,
                "old_status": old_status,
                "new_status": new_status,
                "engine_status": engine_status,
                "note": note,
                "ruleset_version": review.get("ruleset_version", ""),
            }

            path = self.audit_dir / f"{canonical}.jsonl"
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise StorageError(f"无法写入审计记录 {canonical}: {exc}") from exc

            return entry

    def get_review_state(
        self, review_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        canonical = self._canonical_id(review_id)
        with self._lock:
            review = self._read_review_unlocked(canonical)
            audit = self._read_audit_unlocked(canonical)

        latest_by_rule: dict[str, dict[str, Any]] = {}
        for entry in audit:
            rule_id = entry.get("rule_id")
            if rule_id:
                latest_by_rule[rule_id] = entry

        annotations: list[dict[str, Any]] = []
        for result in review.get("results", []):
            entry = latest_by_rule.get(result.get("rule_id"))
            if entry is None:
                continue
            annotations.append(
                {
                    "rule_id": entry["rule_id"],
                    "reviewer": entry["reviewer"],
                    "status": entry["new_status"],
                    "note": entry.get("note"),
                    "timestamp": entry["timestamp"],
                }
            )

        return review, annotations, audit
