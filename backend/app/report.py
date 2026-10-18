from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DISCLAIMER = (
    "本报告由合同初审工具辅助生成，不构成法律意见。"
    "规则命中结果和 AI 建议均需人工复核。"
)

STATUS_LABELS = {
    "pass": "通过",
    "risk": "风险",
    "manual": "需人工确认",
    "not_applicable": "不适用",
}
SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
VERDICT_LABELS = {"pass": "通过", "risk": "风险", "uncertain": "不确定"}
VALID_FINAL_STATUSES = set(STATUS_LABELS)


def _status_label(status: Any) -> str:
    return STATUS_LABELS.get(status, str(status))


def _plain(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _inline(value: Any) -> str:
    text = _plain(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "<br>")


def _cell(value: Any) -> str:
    text = _inline(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    return text.replace("`", "\\`")


def _quote_lines(value: Any) -> list[str]:
    text = _plain(value).replace("\r\n", "\n").replace("\r", "\n")
    return [f"> {line}" for line in text.split("\n")]


def _local_display(value: str) -> str:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def _final_statuses(
    review: dict[str, Any], audit: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in audit:
        rule_id = entry.get("rule_id")
        status = entry.get("new_status")
        if rule_id and status in VALID_FINAL_STATUSES:
            latest[rule_id] = entry

    final: dict[str, str] = {}
    for result in review.get("results", []):
        rule_id = result.get("rule_id")
        entry = latest.get(rule_id)
        final[rule_id] = (
            entry["new_status"] if entry is not None else result.get("status")
        )
    return final, latest


def _summary(
    review: dict[str, Any],
    final: dict[str, str],
    latest: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    counts = {"pass": 0, "risk": 0, "manual": 0, "not_applicable": 0}
    overridden = 0
    results = review.get("results", [])

    for result in results:
        rule_id = result.get("rule_id")
        status = final.get(rule_id)
        if status in counts:
            counts[status] += 1
        annotation = latest.get(rule_id)
        if annotation is not None and status != result.get("status"):
            overridden += 1

    if counts["risk"]:
        conclusion = "存在风险"
    elif counts["manual"]:
        conclusion = "存在待人工确认项"
    else:
        conclusion = "未发现风险"

    return {
        "total": len(results),
        **counts,
        "overridden": overridden,
        "conclusion": conclusion,
    }


def build_json_report(
    review: dict[str, Any],
    audit: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    final, latest = _final_statuses(review, audit)
    results = review.get("results", [])

    rules = []
    for result in results:
        rule_id = result.get("rule_id")
        annotation = latest.get(rule_id)
        rules.append(
            {
                "rule_id": rule_id,
                "name": result.get("name", ""),
                "severity": result.get("severity", ""),
                "description": result.get("description", ""),
                "engine_status": result.get("status"),
                "final_status": final.get(rule_id),
                "evidence": result.get("evidence", []),
                "suggestion": result.get("suggestion", ""),
                "ai": result.get("ai"),
                "annotation": None
                if annotation is None
                else {
                    "reviewer": annotation.get("reviewer", ""),
                    "timestamp": annotation.get("timestamp", ""),
                    "note": annotation.get("note"),
                },
            }
        )

    return {
        "review_id": review.get("review_id", ""),
        "filename": review.get("filename", ""),
        "created_at": review.get("created_at", ""),
        "generated_at": generated_at,
        "ruleset": {
            "version": review.get("ruleset_version", ""),
            "rule_count": len(results),
        },
        "summary": _summary(review, final, latest),
        "rules": rules,
        "audit": audit,
        "disclaimer": DISCLAIMER,
    }


def build_markdown_report(
    review: dict[str, Any],
    audit: list[dict[str, Any]],
    generated_at: str,
) -> str:
    final, latest = _final_statuses(review, audit)
    summary = _summary(review, final, latest)
    results = review.get("results", [])
    name_by_rule = {
        result.get("rule_id"): result.get("name", "") for result in results
    }

    reviewers: list[str] = []
    for entry in audit:
        reviewer = entry.get("reviewer")
        if reviewer and reviewer not in reviewers:
            reviewers.append(reviewer)

    reviewer_text = (
        "、".join(_plain(reviewer) for reviewer in reviewers)
        + "（来自人工标注记录）"
        if reviewers
        else "无人工修改"
    )

    lines: list[str] = [
        "# 合同初审报告",
        "",
        f"- 合同文件：{_inline(review.get('filename', ''))}",
        f"- 审查时间：{_local_display(review.get('created_at', ''))}（本地时间）",
        f"- 规则版本：{_inline(review.get('ruleset_version', ''))}",
        f"- 报告生成：{_local_display(generated_at)}（本地时间）",
        f"- 审核人：{reviewer_text}",
        "",
        "## 一、结论摘要",
        "",
        f"- 总体结论：{summary['conclusion']}",
        f"- 规则总数：{summary['total']}",
        f"- 通过：{summary['pass']}",
        f"- 风险：{summary['risk']}",
        f"- 需人工确认：{summary['manual']}",
        f"- 不适用：{summary['not_applicable']}",
        f"- 人工覆盖：{summary['overridden']} 条",
        "",
        "## 二、逐条结果",
        "",
    ]

    for index, result in enumerate(results, start=1):
        rule_id = result.get("rule_id")
        name = _inline(result.get("name", ""))
        severity = SEVERITY_LABELS.get(
            result.get("severity"), str(result.get("severity", ""))
        )
        entry = latest.get(rule_id)

        lines.append(f"### {index}. {name}（{severity}）")
        lines.append("")
        lines.append(f"- 引擎初判：{_status_label(result.get('status'))}")
        lines.append(f"- 最终结论：{_status_label(final.get(rule_id))}")
        lines.append(f"- 规则说明：{_inline(result.get('description', ''))}")

        evidence = result.get("evidence") or []
        if evidence:
            lines.append("- 命中证据：")
            for item in evidence:
                quote = _quote_lines(item.get("text", ""))
                quote[-1] += (
                    f"（原文偏移 {item.get('start', 0)}–{item.get('end', 0)}）"
                )
                lines.extend(f"  {line}" for line in quote)
        else:
            lines.append(
                "- 命中证据："
                + ("未找到所需条款" if result.get("status") == "risk" else "无")
            )

        if entry is not None:
            lines.append(
                f"- 人工结论：{_status_label(entry.get('new_status'))}"
                f"（{_inline(entry.get('reviewer', ''))}，"
                f"{_inline(entry.get('timestamp', ''))}）"
            )
            if entry.get("note"):
                lines.append(f"- 人工备注：{_inline(entry['note'])}")

        suggestion = _inline(result.get("suggestion", ""))
        lines.append(f"- 整改建议：{suggestion or '无'}")

        ai = result.get("ai")
        if isinstance(ai, dict) and ai.get("mode") == "real":
            verdict = VERDICT_LABELS.get(ai.get("verdict"), ai.get("verdict", ""))
            lines.append(
                f"- AI 建议（需人工复核）：{verdict} — "
                f"{_inline(ai.get('reason', ''))}"
            )

        lines.append("")

    lines.extend(["## 三、人工修改审计", ""])
    if audit:
        lines.append("| 时间（UTC） | 审核人 | 规则 | 原值 | 新值 | 备注 |")
        lines.append("|---|---|---|---|---|---|")
        for entry in audit:
            rule_name = name_by_rule.get(
                entry.get("rule_id"), entry.get("rule_id", "")
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(entry.get("timestamp", "")),
                        _cell(entry.get("reviewer", "")),
                        _cell(rule_name),
                        _cell(entry.get("old_status", "")),
                        _cell(entry.get("new_status", "")),
                        _cell(entry.get("note") or "—"),
                    ]
                )
                + " |"
            )
    else:
        lines.append("无人工修改记录。")

    lines.extend(["", "## 四、声明", "", DISCLAIMER, ""])
    return "\n".join(lines)


def report_filename(
    review: dict[str, Any], report_format: str, generated_at: str
) -> str:
    stem = Path(str(review.get("filename") or "合同")).stem or "合同"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .") or "合同"
    stem = stem[:60]

    try:
        moment = datetime.fromisoformat(
            str(generated_at).replace("Z", "+00:00")
        )
        stamp = moment.strftime("%Y%m%d-%H%M%S")
    except (ValueError, TypeError):
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    extension = "json" if report_format == "json" else "md"
    return f"审查报告_{stem}_{stamp}.{extension}"
