from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

Status = Literal["pass", "risk", "manual"]
Severity = Literal["high", "medium", "low"]
Operator = Literal["keyword", "regex"]
Expectation = Literal["present", "absent"]
MatchMode = Literal["any", "all"]
RegexFlag = Literal["i", "m", "s", "x"]

FLAG_MAP: dict[str, int] = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
}


class RuleConfigError(Exception):
    """Raised when the YAML rule file is missing or invalid."""


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Severity
    expect: Expectation
    operator: Operator
    keywords: list[str] | None = None
    match_mode: MatchMode = "any"
    pattern: str | None = None
    flags: list[RegexFlag] = Field(default_factory=list)
    on_match: Status | None = None
    on_miss: Status | None = None
    suggestion: str = ""
    llm_fallback: bool = False
    evidence_max: int = Field(default=5, ge=1, le=20)

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [keyword.strip() for keyword in value]
        if not cleaned or any(not keyword for keyword in cleaned):
            raise ValueError("keywords must be non-empty strings")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("keywords must be unique")
        return cleaned

    @field_validator("flags")
    @classmethod
    def _unique_flags(cls, value: list[RegexFlag]) -> list[RegexFlag]:
        if len(set(value)) != len(value):
            raise ValueError("flags must be unique")
        return value

    @model_validator(mode="after")
    def _validate_operator_fields(self) -> "Rule":
        if self.operator == "keyword":
            if not self.keywords:
                raise ValueError("keyword operator requires a non-empty keywords list")
            if self.pattern is not None:
                raise ValueError("keyword operator must not define pattern")
            if self.flags:
                raise ValueError("keyword operator must not define flags")
        else:
            if not self.pattern:
                raise ValueError("regex operator requires a non-empty pattern")
            if self.keywords is not None:
                raise ValueError("regex operator must not define keywords")
            flags = 0
            for flag in self.flags:
                flags |= FLAG_MAP[flag]
            try:
                re.compile(self.pattern, flags)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern: {exc}") from exc
        return self

    @property
    def match_status(self) -> Status:
        if self.on_match is not None:
            return self.on_match
        return "pass" if self.expect == "present" else "risk"

    @property
    def miss_status(self) -> Status:
        if self.on_miss is not None:
            return self.on_miss
        return "risk" if self.expect == "present" else "pass"


class Ruleset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    name: str = Field(default="合同审查规则", min_length=1)
    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> "Ruleset":
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule ids must be unique")
        return self


@dataclass(frozen=True)
class CompiledRule:
    rule: Rule
    regex: re.Pattern[str] | None
    keyword_patterns: tuple[tuple[str, re.Pattern[str]], ...]


@dataclass(frozen=True)
class CompiledRuleset:
    ruleset: Ruleset
    version: str
    path: Path
    mtime_ns: int
    size: int
    rules: tuple[CompiledRule, ...]

    @property
    def rule_count(self) -> int:
        return len(self.rules)


def _format_validation_error(exc: ValidationError) -> str:
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        details.append(f"{location}: {error['msg']}")
    return "规则配置校验失败: " + "; ".join(details)


def _compile_rule(rule: Rule) -> CompiledRule:
    if rule.operator == "regex":
        assert rule.pattern is not None
        flags = 0
        for flag in rule.flags:
            flags |= FLAG_MAP[flag]
        return CompiledRule(
            rule=rule,
            regex=re.compile(rule.pattern, flags),
            keyword_patterns=(),
        )

    assert rule.keywords
    return CompiledRule(
        rule=rule,
        regex=None,
        keyword_patterns=tuple(
            (keyword, re.compile(re.escape(keyword), re.IGNORECASE))
            for keyword in rule.keywords
        ),
    )


def load_ruleset(path: Path) -> CompiledRuleset:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RuleConfigError(f"无法读取规则文件 {path}: {exc}") from exc

    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RuleConfigError(f"规则文件不是合法的 UTF-8: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RuleConfigError(f"规则 YAML 解析失败: {exc}") from exc

    if not isinstance(document, dict):
        raise RuleConfigError("规则文件顶层必须是 YAML 对象")

    try:
        ruleset = Ruleset.model_validate(document)
    except ValidationError as exc:
        raise RuleConfigError(_format_validation_error(exc)) from exc

    stat = path.stat()
    version = "sha256:" + hashlib.sha256(raw).hexdigest()[:12]
    return CompiledRuleset(
        ruleset=ruleset,
        version=version,
        path=path,
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
        rules=tuple(_compile_rule(rule) for rule in ruleset.rules),
    )


class RuleStore:
    """Loads and caches rules, reloading when the file signature changes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cached: CompiledRuleset | None = None
        self._signature: tuple[int, int] | None = None
        self.get()

    def _file_signature(self) -> tuple[int, int]:
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise RuleConfigError(f"无法读取规则文件 {self.path}: {exc}") from exc
        return stat.st_mtime_ns, stat.st_size

    def get(self) -> CompiledRuleset:
        signature = self._file_signature()
        with self._lock:
            if self._cached is None or signature != self._signature:
                loaded = load_ruleset(self.path)
                self._cached = loaded
                self._signature = (loaded.mtime_ns, loaded.size)
            return self._cached
