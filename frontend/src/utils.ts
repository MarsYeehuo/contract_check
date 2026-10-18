import type { AIInfo, EffectiveStatus, Severity } from "./types";

const STATUS_LABELS: Record<EffectiveStatus, string> = {
  pass: "通过",
  risk: "风险",
  manual: "需人工确认",
  not_applicable: "不适用",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const VERDICT_LABELS: Record<AIInfo["verdict"], string> = {
  pass: "倾向通过",
  risk: "倾向风险",
  uncertain: "不确定",
};

export function statusLabel(status: EffectiveStatus): string {
  return STATUS_LABELS[status];
}

export function verdictLabel(verdict: AIInfo["verdict"]): string {
  return VERDICT_LABELS[verdict];
}

export function severityLabel(severity: Severity): string {
  return SEVERITY_LABELS[severity];
}

export function formatCount(value: number): string {
  return value.toLocaleString("zh-CN");
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function downloadTextFile(
  content: string,
  mime: string,
  filename: string,
): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
