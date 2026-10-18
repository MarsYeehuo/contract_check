from __future__ import annotations

from dataclasses import dataclass

from .operators import Evidence, evaluate_rule
from .rules import RuleStore, Status


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    description: str
    severity: str
    operator: str
    status: Status
    matched: bool
    match_count: int
    evidence: tuple[Evidence, ...]
    suggestion: str
    llm_eligible: bool


@dataclass(frozen=True)
class Evaluation:
    ruleset_version: str
    rule_count: int
    results: tuple[RuleResult, ...]
    summary: dict[str, int]


class RuleEngine:
    def __init__(self, store: RuleStore):
        self._store = store

    def evaluate(self, text: str) -> Evaluation:
        ruleset = self._store.get()
        results: list[RuleResult] = []
        summary = {"total": 0, "pass": 0, "risk": 0, "manual": 0}

        for compiled in ruleset.rules:
            operator_result = evaluate_rule(compiled, text)
            rule = compiled.rule
            status = (
                rule.match_status if operator_result.matched else rule.miss_status
            )

            for evidence in operator_result.evidence:
                if text[evidence.start : evidence.end] != evidence.text:
                    raise RuntimeError(
                        f"evidence offset invariant violated for rule {rule.id}: "
                        f"{evidence.start}:{evidence.end}"
                    )

            result = RuleResult(
                rule_id=rule.id,
                name=rule.name,
                description=rule.description,
                severity=rule.severity,
                operator=rule.operator,
                status=status,
                matched=operator_result.matched,
                match_count=operator_result.match_count,
                evidence=operator_result.evidence,
                suggestion=rule.suggestion,
                llm_eligible=rule.llm_fallback and not operator_result.matched,
            )
            results.append(result)
            summary["total"] += 1
            summary[status] += 1

        return Evaluation(
            ruleset_version=ruleset.version,
            rule_count=ruleset.rule_count,
            results=tuple(results),
            summary=summary,
        )
