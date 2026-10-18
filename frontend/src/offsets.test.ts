import { describe, expect, it } from "vitest";

import { buildSegments, sliceByCodePoints } from "./offsets";
import type { Evidence } from "./types";

function evidence(start: number, end: number, text: string): Evidence {
  return { start, end, text, operator: "keyword", keyword: null };
}

describe("sliceByCodePoints", () => {
  it("按 Unicode 码点切片中文与 emoji", () => {
    const text = "甲方😀乙方";
    expect(sliceByCodePoints(text, 0, 2)).toBe("甲方");
    expect(sliceByCodePoints(text, 2, 3)).toBe("😀");
    expect(sliceByCodePoints(text, 3, 5)).toBe("乙方");
  });

  it("越界与空区间安全返回", () => {
    expect(sliceByCodePoints("abc", -5, 2)).toBe("ab");
    expect(sliceByCodePoints("abc", 2, 99)).toBe("c");
    expect(sliceByCodePoints("abc", 2, 1)).toBe("");
  });
});

describe("buildSegments", () => {
  it("无证据时整段返回", () => {
    expect(buildSegments("合同文本", [])).toEqual([
      { text: "合同文本", evidenceIndex: null, start: 0 },
    ]);
  });

  it("多条证据分段并保留码点索引", () => {
    const segments = buildSegments("甲方😀乙方", [
      evidence(1, 2, "方"),
      evidence(3, 5, "乙方"),
    ]);
    expect(segments).toEqual([
      { text: "甲", evidenceIndex: null, start: 0 },
      { text: "方", evidenceIndex: 0, start: 1 },
      { text: "😀", evidenceIndex: null, start: 2 },
      { text: "乙方", evidenceIndex: 1, start: 3 },
    ]);
  });

  it("重叠证据合并并保留首个索引", () => {
    const segments = buildSegments("abcdef", [
      evidence(1, 4, "bcd"),
      evidence(3, 5, "de"),
    ]);
    expect(segments).toEqual([
      { text: "a", evidenceIndex: null, start: 0 },
      { text: "bcde", evidenceIndex: 0, start: 1 },
      { text: "f", evidenceIndex: null, start: 5 },
    ]);
  });

  it("包含关系与越界区间被安全处理", () => {
    const segments = buildSegments("abcdef", [
      evidence(1, 5, "bcde"),
      evidence(2, 3, "c"),
      evidence(4, 99, "ef"),
    ]);
    expect(segments).toEqual([
      { text: "a", evidenceIndex: null, start: 0 },
      { text: "bcdef", evidenceIndex: 0, start: 1 },
    ]);
  });

  it("空文本返回空数组", () => {
    expect(buildSegments("", [evidence(0, 1, "x")])).toEqual([]);
  });

  it("分段重建后的文本与原文完全一致", () => {
    const text = "甲😀乙\r\n丙";
    const segments = buildSegments(text, [
      evidence(0, 2, "甲😀"),
      evidence(4, 5, "丙"),
    ]);
    expect(segments.map((segment) => segment.text).join("")).toBe(text);
  });
});
