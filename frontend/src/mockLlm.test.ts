import { describe, expect, it } from "vitest";

import { buildMockAssessments } from "./mockLlm";
import type { RuleResult } from "./types";

function rule(overrides: Partial<RuleResult>): RuleResult {
  return {
    rule_id: "ip_ownership",
    name: "知识产权归属",
    description: "合同应明确约定知识产权归属",
    severity: "high",
    operator: "keyword",
    status: "risk",
    matched: false,
    match_count: 0,
    evidence: [],
    suggestion: "",
    llm_eligible: true,
    ai: null,
    ...overrides,
  };
}

describe("buildMockAssessments", () => {
  it("命中同义词时给出 pass 与准确证据偏移", () => {
    const text = "甲方😀乙方，技术成果归甲方所有。";
    const assessments = buildMockAssessments([rule({})], text);

    const ai = assessments.ip_ownership;
    expect(ai.mode).toBe("mock");
    expect(ai.verdict).toBe("pass");
    expect(ai.review_required).toBe(true);
    expect(ai.quote).toBe("技术成果");
    expect(ai.evidence[0].start).toBe(Array.from(text).indexOf("技"));
    expect(ai.evidence[0].text).toBe("技术成果");
  });

  it("未命中同义词时返回 uncertain 且无证据", () => {
    const assessments = buildMockAssessments(
      [rule({ rule_id: "confidentiality", name: "保密义务" })],
      "本合同未涉及相关约定。",
    );

    expect(assessments.confidentiality.verdict).toBe("uncertain");
    expect(assessments.confidentiality.evidence).toEqual([]);
  });

  it("只处理未命中的可兜底规则", () => {
    const assessments = buildMockAssessments(
      [
        rule({ rule_id: "ip_ownership" }),
        rule({ rule_id: "payment_term", llm_eligible: false }),
        rule({ rule_id: "confidentiality", matched: true }),
      ],
      "技术成果",
    );

    expect(Object.keys(assessments)).toEqual(["ip_ownership"]);
  });

  it("未知规则给出 uncertain 而不是崩溃", () => {
    const assessments = buildMockAssessments(
      [rule({ rule_id: "custom_rule", name: "自定义规则" })],
      "文本",
    );
    expect(assessments.custom_rule.verdict).toBe("uncertain");
  });
});
