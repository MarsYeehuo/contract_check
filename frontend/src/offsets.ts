import type { Evidence } from "./types";

export interface Segment {
  text: string;
  evidenceIndex: number | null;
  start: number;
}

export function sliceByCodePoints(
  text: string,
  start: number,
  end: number,
): string {
  const characters = Array.from(text);
  const from = Math.max(0, Math.trunc(start));
  const to = Math.min(characters.length, Math.trunc(end));
  if (to <= from) {
    return "";
  }
  return characters.slice(from, to).join("");
}

export function buildSegments(
  text: string,
  evidences: Evidence[],
): Segment[] {
  const characters = Array.from(text);
  if (characters.length === 0) {
    return [];
  }

  const ranges = evidences
    .map((evidence, index) => ({
      start: Math.max(0, Math.trunc(evidence.start)),
      end: Math.min(characters.length, Math.trunc(evidence.end)),
      index,
    }))
    .filter(
      (range) =>
        Number.isFinite(range.start) &&
        Number.isFinite(range.end) &&
        range.end > range.start,
    )
    .sort((a, b) => a.start - b.start || a.end - b.end);

  const segments: Segment[] = [];
  let cursor = 0;

  for (const range of ranges) {
    if (range.start < cursor) {
      const previous = segments[segments.length - 1];
      if (
        previous &&
        previous.evidenceIndex !== null &&
        range.end > cursor
      ) {
        previous.text += characters.slice(cursor, range.end).join("");
        cursor = range.end;
      }
      continue;
    }

    if (range.start > cursor) {
      segments.push({
        text: characters.slice(cursor, range.start).join(""),
        evidenceIndex: null,
        start: cursor,
      });
    }

    segments.push({
      text: characters.slice(range.start, range.end).join(""),
      evidenceIndex: range.index,
      start: range.start,
    });
    cursor = range.end;
  }

  if (cursor < characters.length) {
    segments.push({
      text: characters.slice(cursor).join(""),
      evidenceIndex: null,
      start: cursor,
    });
  }

  return segments;
}
