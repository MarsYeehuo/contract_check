import { useState } from "react";

import type {
  AIInfo,
  Annotation,
  AnnotationStatus,
  EffectiveStatus,
  RuleResult,
} from "../types";
import { severityLabel, statusLabel, verdictLabel } from "../utils";

interface RuleCardProps {
  result: RuleResult;
  annotation?: Annotation;
  ai: AIInfo | null;
  effectiveStatus: EffectiveStatus;
  active: boolean;
  saving: boolean;
  onSelect: () => void;
  onEvidenceSelect: (index: number) => void;
  onAnnotate: (status: AnnotationStatus, note: string) => void;
}

const STATUS_OPTIONS: Array<{ value: AnnotationStatus; label: string }> = [
  { value: "pass", label: "通过" },
  { value: "risk", label: "风险" },
  { value: "not_applicable", label: "不适用" },
];

function initialStatus(
  annotation: Annotation | undefined,
  engineStatus: RuleResult["status"],
): AnnotationStatus | "" {
  if (annotation) {
    return annotation.status;
  }
  return engineStatus === "manual" ? "" : engineStatus;
}

export function RuleCard({
  result,
  annotation,
  ai,
  effectiveStatus,
  active,
  saving,
  onSelect,
  onEvidenceSelect,
  onAnnotate,
}: RuleCardProps) {
  const [statusDraft, setStatusDraft] = useState<AnnotationStatus | "">(
    initialStatus(annotation, result.status),
  );
  const [noteDraft, setNoteDraft] = useState(annotation?.note ?? "");

  const unchanged = statusDraft === "" || statusDraft === effectiveStatus;
  const overridden = annotation !== undefined && annotation.status !== result.status;

  return (
    <article
      className={active ? "rule-card active" : "rule-card"}
      onClick={onSelect}
    >
      <header className="rule-head">
        <div className="rule-title">
          <span className={`severity severity-${result.severity}`}>
            {severityLabel(result.severity)}
          </span>
          <h3>{result.name}</h3>
        </div>
        <div className="rule-badges">
          <span className={`badge status-${result.status}`}>
            {statusLabel(result.status)}
          </span>
          {overridden && <span className="badge badge-override">已人工覆盖</span>}
        </div>
      </header>

      <p className="rule-description">{result.description}</p>

      <div className="rule-meta">
        <span>算子：{result.operator === "keyword" ? "关键词" : "正则"}</span>
        <span>命中次数：{result.match_count}</span>
        <span>当前有效：{statusLabel(effectiveStatus)}</span>
      </div>

      <div className="evidence-block">
        <h4>命中证据</h4>
        {result.evidence.length > 0 ? (
          <ul className="evidence-list">
            {result.evidence.map((item, index) => (
              <li key={`${item.start}-${item.end}-${index}`}>
                <button
                  type="button"
                  className="evidence-link"
                  title="在原文中定位"
                  onClick={(event) => {
                    event.stopPropagation();
                    onEvidenceSelect(index);
                  }}
                >
                  <span className="evidence-text">“{item.text}”</span>
                  <span className="evidence-offset">
                    偏移 {item.start}–{item.end} · 定位
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            {result.status === "risk" ? "未找到所需条款" : "无命中证据"}
          </p>
        )}
      </div>

      <p className="rule-suggestion">
        <strong>整改建议：</strong>
        {result.suggestion || "无"}
      </p>

      {ai && (
        <div
          className={ai.mode === "mock" ? "ai-block ai-block-mock" : "ai-block"}
        >
          <div className="ai-head">
            <strong>AI 判断，需人工复核</strong>
            <span className="ai-badges">
              <span
                className={
                  ai.mode === "mock" ? "badge badge-mock" : "badge badge-ai"
                }
              >
                {ai.mode === "mock" ? "前端模拟" : "AI 建议"}
              </span>
              <span className={`badge ai-verdict ai-verdict-${ai.verdict}`}>
                {verdictLabel(ai.verdict)}
              </span>
            </span>
          </div>
          <p className="ai-reason">{ai.reason}</p>
          {ai.quote && <p className="ai-quote">引用：“{ai.quote}”</p>}
          <p className="ai-note">
            {ai.mode === "mock"
              ? "本地模拟结果仅用于演示，不会写入审计或报告。"
              : `模型 ${ai.model} · AI 不改变引擎结论`}
          </p>
        </div>
      )}

      {annotation && (
        <div className="annotation-summary">
          <div>
            人工结论：<strong>{statusLabel(annotation.status)}</strong> ·{" "}
            {annotation.reviewer} · {annotation.timestamp}
          </div>
          {annotation.note && (
            <div className="annotation-note">备注：{annotation.note}</div>
          )}
        </div>
      )}

      <form
        className="annotation-form"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!unchanged) {
            onAnnotate(statusDraft, noteDraft.trim());
          }
        }}
      >
        <label>
          <span>人工结论</span>
          <select
            value={statusDraft}
            onChange={(event) =>
              setStatusDraft(event.target.value as AnnotationStatus | "")
            }
          >
            <option value="">请选择</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="note-field">
          <span>备注</span>
          <input
            value={noteDraft}
            maxLength={500}
            placeholder="可选，最多 500 字"
            onChange={(event) => setNoteDraft(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="button button-secondary"
          disabled={unchanged || saving}
        >
          {saving ? "保存中…" : "保存结论"}
        </button>
      </form>
    </article>
  );
}
