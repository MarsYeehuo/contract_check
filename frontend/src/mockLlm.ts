import type { AIInfo, RuleResult } from "./types";

const SYNONYMS: Record<string, string[]> = {
  ip_ownership: ["版权", "技术成果", "归属"],
  payment_term: ["账期", "发票后"],
  dispute_resolution: ["法院", "仲裁委员会", "裁决"],
  confidentiality: ["秘密", "NDA"],
};

const MOCK_MODEL = "frontend-mock";

function codePointIndex(text: string, needle: string): number {
  const index = text.indexOf(needle);
  if (index < 0) {
    return -1;
  }
  return Array.from(text.slice(0, index)).length;
}

function buildEvidence(text: string, quote: string) {
  const start = codePointIndex(text, quote);
  if (start < 0) {
    return [];
  }
  return [
    {
      start,
      end: start + Array.from(quote).length,
      text: quote,
      operator: "keyword" as const,
      keyword: quote,
    },
  ];
}

export function buildMockAssessments(
  results: RuleResult[],
  text: string,
): Record<string, AIInfo> {
  const assessments: Record<string, AIInfo> = {};

  for (const result of results) {
    if (!result.llm_eligible || result.matched) {
      continue;
    }

    const synonyms = SYNONYMS[result.rule_id] ?? [];
    const hit = synonyms.find((word) => text.includes(word));

    if (hit) {
      assessments[result.rule_id] = {
        mode: "mock",
        verdict: "pass",
        reason: `本地模拟：合同中出现了「${hit}」，可能满足该规则，请人工确认。`,
        quote: hit,
        evidence: buildEvidence(text, hit),
        review_required: true,
        model: MOCK_MODEL,
      };
    } else {
      assessments[result.rule_id] = {
        mode: "mock",
        verdict: "uncertain",
        reason: `本地模拟：未找到与「${result.name}」相关的同义词，建议人工复核。`,
        quote: "",
        evidence: [],
        review_required: true,
        model: MOCK_MODEL,
      };
    }
  }

  return assessments;
}
