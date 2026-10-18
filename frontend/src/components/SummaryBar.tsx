interface SummaryBarProps {
  summary: Record<string, number>;
  annotatedCount: number;
  rulesetVersion: string;
  llmStatus: string;
  mockAiCount: number;
}

const LLM_LABELS: Record<string, string> = {
  disabled: "AI：已关闭",
  not_needed: "AI：未触发",
  no_key: "AI：未配置 Key",
  ok: "AI：已启用",
  error: "AI：调用异常",
};

export function SummaryBar({
  summary,
  annotatedCount,
  rulesetVersion,
  llmStatus,
  mockAiCount,
}: SummaryBarProps) {
  return (
    <section className="panel summary-panel">
      <div className="summary-head">
        <h2>审查摘要</h2>
        <span className="muted">规则版本 {rulesetVersion}</span>
      </div>
      <div className="summary-counts">
        <span className="summary-item">共 {summary.total} 条</span>
        <span className="summary-item status-pass">通过 {summary.pass}</span>
        <span className="summary-item status-risk">风险 {summary.risk}</span>
        <span className="summary-item status-manual">
          需人工确认 {summary.manual}
        </span>
      </div>
      <div className="summary-footer">
        <span className="muted">
          {mockAiCount > 0
            ? `AI：未配置 Key（前端模拟 ${mockAiCount} 条）`
            : (LLM_LABELS[llmStatus] ?? llmStatus)}
        </span>
        {annotatedCount > 0 && (
          <span className="badge badge-override">
            已人工标注 {annotatedCount} 条
          </span>
        )}
      </div>
    </section>
  );
}
