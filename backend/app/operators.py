from __future__ import annotations

from dataclasses import dataclass

from .rules import CompiledRule


@dataclass(frozen=True)
class Evidence:
    start: int
    end: int
    text: str
    operator: str
    keyword: str | None = None


@dataclass(frozen=True)
class OperatorResult:
    matched: bool
    evidence: tuple[Evidence, ...]
    match_count: int


def evaluate_rule(rule: CompiledRule, text: str) -> OperatorResult:
    if rule.rule.operator == "regex":
        return _evaluate_regex(rule, text)
    return _evaluate_keyword(rule, text)


def _evaluate_keyword(rule: CompiledRule, text: str) -> OperatorResult:
    raw_matches: list[tuple[int, int, str]] = []
    found_keywords: set[str] = set()

    for keyword, pattern in rule.keyword_patterns:
        for match in pattern.finditer(text):
            if match.start() == match.end():
                continue
            found_keywords.add(keyword)
            raw_matches.append((match.start(), match.end(), keyword))

    raw_matches.sort(key=lambda item: (item[0], item[1], item[2]))
    deduped: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()
    for start, end, keyword in raw_matches:
        if (start, end) in seen:
            continue
        seen.add((start, end))
        deduped.append((start, end, keyword))

    if rule.rule.match_mode == "all":
        matched = len(found_keywords) == len(rule.keyword_patterns)
    else:
        matched = bool(deduped)

    evidence = tuple(
        Evidence(
            start=start,
            end=end,
            text=text[start:end],
            operator="keyword",
            keyword=keyword,
        )
        for start, end, keyword in deduped[: rule.rule.evidence_max]
    )
    return OperatorResult(
        matched=matched,
        evidence=evidence,
        match_count=len(deduped),
    )


def _evaluate_regex(rule: CompiledRule, text: str) -> OperatorResult:
    assert rule.regex is not None

    raw_matches: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for match in rule.regex.finditer(text):
        if match.start() == match.end():
            continue
        key = (match.start(), match.end())
        if key in seen:
            continue
        seen.add(key)
        raw_matches.append(key)

    raw_matches.sort()
    evidence = tuple(
        Evidence(
            start=start,
            end=end,
            text=text[start:end],
            operator="regex",
            keyword=None,
        )
        for start, end in raw_matches[: rule.rule.evidence_max]
    )
    return OperatorResult(
        matched=bool(raw_matches),
        evidence=evidence,
        match_count=len(raw_matches),
    )
