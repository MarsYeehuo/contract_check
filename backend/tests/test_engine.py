from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.engine import RuleEngine
from app.rules import RuleConfigError, RuleStore, load_ruleset

BACKEND_DIR = Path(__file__).resolve().parents[1]
RULES_PATH = BACKEND_DIR / "rules" / "review_rules.yaml"
SAMPLES_DIR = BACKEND_DIR / "samples"


def _rule(**overrides):
    rule = {
        "id": "test_rule",
        "name": "测试规则",
        "description": "测试规则描述",
        "severity": "medium",
        "expect": "present",
        "operator": "keyword",
        "keywords": ["测试"],
    }
    rule.update(overrides)
    return rule


def _write_rules(path: Path, rules: list[dict]) -> Path:
    document = {"version": 1, "name": "测试规则集", "rules": rules}
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _evaluate(tmp_path: Path, rules: list[dict], text: str):
    rules_path = _write_rules(tmp_path / "rules.yaml", rules)
    engine = RuleEngine(RuleStore(rules_path))
    return engine.evaluate(text)


def _sample_text(name: str) -> str:
    return (SAMPLES_DIR / name).read_text(encoding="utf-8")


def test_builtin_rules_load():
    ruleset = load_ruleset(RULES_PATH)

    assert ruleset.rule_count == 6
    assert ruleset.version.startswith("sha256:")
    assert {compiled.rule.id for compiled in ruleset.rules} == {
        "penalty_ratio",
        "ip_ownership",
        "payment_term",
        "dispute_resolution",
        "confidentiality",
        "auto_renewal",
    }


def test_sample_pass_all_pass():
    engine = RuleEngine(RuleStore(RULES_PATH))
    evaluation = engine.evaluate(_sample_text("sample_pass.txt"))

    assert evaluation.summary == {
        "total": 6,
        "pass": 6,
        "risk": 0,
        "manual": 0,
    }
    assert all(result.status == "pass" for result in evaluation.results)
    assert all(not result.llm_eligible for result in evaluation.results)


def test_sample_risk_expected_matrix():
    engine = RuleEngine(RuleStore(RULES_PATH))
    evaluation = engine.evaluate(_sample_text("sample_risk.txt"))
    results = {result.rule_id: result for result in evaluation.results}

    assert evaluation.summary == {
        "total": 6,
        "pass": 3,
        "risk": 2,
        "manual": 1,
    }
    assert results["penalty_ratio"].status == "risk"
    assert results["penalty_ratio"].matched is True
    assert results["penalty_ratio"].evidence
    assert "50%" in results["penalty_ratio"].evidence[0].text

    assert results["ip_ownership"].status == "risk"
    assert results["ip_ownership"].matched is False
    assert results["ip_ownership"].llm_eligible is True
    assert results["ip_ownership"].evidence == ()

    assert results["auto_renewal"].status == "manual"
    assert results["auto_renewal"].matched is True

    for result in evaluation.results:
        for evidence in result.evidence:
            text = _sample_text("sample_risk.txt")
            assert text[evidence.start : evidence.end] == evidence.text


def test_keyword_any_match_and_offsets(tmp_path):
    rules = [
        _rule(
            id="ip_rule",
            name="知识产权",
            keywords=["知识产权", "著作权"],
            expect="present",
        )
    ]
    text = "前言。本合同的著作权归甲方所有。"

    evaluation = _evaluate(tmp_path, rules, text)

    result = evaluation.results[0]
    assert result.matched is True
    assert result.status == "pass"
    assert result.match_count == 1
    assert result.evidence[0].keyword == "著作权"
    assert text[result.evidence[0].start : result.evidence[0].end] == "著作权"


def test_keyword_all_requires_every_keyword_and_keeps_partial_evidence(tmp_path):
    rules = [
        _rule(
            id="both_parties",
            name="双方义务",
            keywords=["甲方", "乙方"],
            match_mode="all",
            expect="present",
        )
    ]

    partial = _evaluate(tmp_path, rules, "甲方应履行义务。").results[0]
    assert partial.matched is False
    assert partial.status == "risk"
    assert partial.evidence and partial.evidence[0].keyword == "甲方"

    complete = _evaluate(tmp_path, rules, "甲方和乙方均应履行义务。").results[0]
    assert complete.matched is True
    assert complete.status == "pass"
    assert {evidence.keyword for evidence in complete.evidence} == {"甲方", "乙方"}


def test_keyword_is_case_insensitive(tmp_path):
    rules = [
        _rule(
            id="nda_rule",
            name="NDA",
            keywords=["nda"],
            expect="present",
        )
    ]

    result = _evaluate(tmp_path, rules, "双方签署了 NDA 协议。").results[0]

    assert result.matched is True
    assert result.status == "pass"


def test_expect_absent_status(tmp_path):
    rules = [
        _rule(
            id="no_auto",
            name="禁止自动续约",
            operator="regex",
            keywords=None,
            pattern="自动续约",
            expect="absent",
        )
    ]

    hit = _evaluate(tmp_path, rules, "合同自动续约一年。").results[0]
    miss = _evaluate(tmp_path, rules, "合同到期终止。").results[0]

    assert hit.matched is True
    assert hit.status == "risk"
    assert miss.matched is False
    assert miss.status == "pass"


def test_status_overrides_to_manual(tmp_path):
    rules = [
        _rule(
            id="manual_rule",
            name="需人工确认",
            on_match="manual",
            on_miss="pass",
        )
    ]

    hit = _evaluate(tmp_path, rules, "测试条款").results[0]
    miss = _evaluate(tmp_path, rules, "其他条款").results[0]

    assert hit.status == "manual"
    assert miss.status == "pass"


def test_evidence_limit_and_match_count(tmp_path):
    rules = [
        _rule(
            id="repeat_rule",
            name="重复命中",
            keywords=["违约"],
            evidence_max=2,
            expect="absent",
        )
    ]
    text = "违约" * 5

    result = _evaluate(tmp_path, rules, text).results[0]

    assert result.match_count == 5
    assert len(result.evidence) == 2
    assert result.status == "risk"
    for evidence in result.evidence:
        assert text[evidence.start : evidence.end] == "违约"


def test_regex_multiple_matches_and_limit(tmp_path):
    rules = [
        _rule(
            id="percent_rule",
            name="百分比",
            operator="regex",
            keywords=None,
            pattern=r"\d+%",
            evidence_max=2,
            expect="absent",
        )
    ]
    text = "比例分别为 10%、20%、30%。"

    result = _evaluate(tmp_path, rules, text).results[0]

    assert result.match_count == 3
    assert len(result.evidence) == 2
    assert result.status == "risk"


def test_regex_flags(tmp_path):
    rules = [
        _rule(
            id="flag_rule",
            name="不区分大小写",
            operator="regex",
            keywords=None,
            pattern="nda",
            flags=["i"],
            expect="present",
        )
    ]

    result = _evaluate(tmp_path, rules, "已签署 NDA。").results[0]

    assert result.matched is True
    assert result.status == "pass"


def test_zero_width_regex_matches_are_ignored(tmp_path):
    rules = [
        _rule(
            id="lookahead_rule",
            name="零宽断言",
            operator="regex",
            keywords=None,
            pattern="(?=仲裁)",
            expect="present",
        )
    ]

    result = _evaluate(tmp_path, rules, "提交仲裁。").results[0]

    assert result.matched is False
    assert result.match_count == 0
    assert result.evidence == ()
    assert result.status == "risk"


def test_offset_invariant_with_emoji(tmp_path):
    rules = [
        _rule(
            id="emoji_rule",
            name="违约金",
            keywords=["违约金"],
            expect="absent",
        )
    ]
    text = "前言😀\n违约金为合同总金额的50%。"

    result = _evaluate(tmp_path, rules, text).results[0]

    assert result.evidence
    evidence = result.evidence[0]
    assert evidence.start == len("前言😀\n")
    assert text[evidence.start : evidence.end] == "违约金"
    assert evidence.text == "违约金"


def test_rule_store_hot_reload(tmp_path):
    rules_path = _write_rules(
        tmp_path / "rules.yaml",
        [_rule(id="first_rule", name="第一条", keywords=["保密"])],
    )
    store = RuleStore(rules_path)
    engine = RuleEngine(store)

    first = engine.evaluate("本合同保密。")
    assert len(first.results) == 1

    _write_rules(
        rules_path,
        [
            _rule(id="first_rule", name="第一条", keywords=["保密"]),
            _rule(id="second_rule", name="第二条", keywords=["仲裁"]),
        ],
    )

    second = engine.evaluate("本合同保密，争议提交仲裁。")
    assert len(second.results) == 2
    assert {result.rule_id for result in second.results} == {
        "first_rule",
        "second_rule",
    }
    assert store.get().rule_count == 2


@pytest.mark.parametrize(
    "ruleset",
    [
        {
            "version": 1,
            "name": "重复 ID",
            "rules": [
                _rule(id="dup_rule", name="一"),
                _rule(id="dup_rule", name="二"),
            ],
        },
        {
            "version": 1,
            "name": "非法正则",
            "rules": [
                _rule(
                    id="bad_regex",
                    operator="regex",
                    keywords=None,
                    pattern="(",
                )
            ],
        },
        {
            "version": 1,
            "name": "关键词缺失",
            "rules": [
                _rule(id="no_keywords", keywords=None),
            ],
        },
        {
            "version": 1,
            "name": "未知字段",
            "rules": [
                _rule(id="unknown_field", unknown_field=True),
            ],
        },
        {
            "version": 1,
            "name": "正则误带关键词",
            "rules": [
                _rule(
                    id="regex_with_keywords",
                    operator="regex",
                    pattern="仲裁",
                    keywords=["仲裁"],
                )
            ],
        },
        {
            "version": 1,
            "name": "关键词误带 flags",
            "rules": [
                _rule(id="keyword_with_flags", flags=["i"]),
            ],
        },
        {
            "version": 1,
            "name": "正则缺少 pattern",
            "rules": [
                _rule(
                    id="missing_pattern",
                    operator="regex",
                    keywords=None,
                    pattern=None,
                )
            ],
        },
    ],
)
def test_invalid_rules_are_rejected(tmp_path, ruleset):
    rules_path = tmp_path / "invalid.yaml"
    rules_path.write_text(
        yaml.safe_dump(ruleset, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(RuleConfigError):
        load_ruleset(rules_path)


def test_unknown_field_is_rejected_at_top_level(tmp_path):
    rules_path = tmp_path / "invalid_top.yaml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "name": "顶层未知字段",
                "rules": [_rule()],
                "unexpected": True,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuleConfigError):
        load_ruleset(rules_path)
