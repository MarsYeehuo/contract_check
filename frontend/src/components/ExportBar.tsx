import type { ReportFormat } from "../types";

interface ExportBarProps {
  auditCount: number;
  pendingManual: number;
  mockAiCount: number;
  exporting: ReportFormat | null;
  onOpenAudit: () => void;
  onExport: (format: ReportFormat) => void;
}

export function ExportBar({
  auditCount,
  pendingManual,
  mockAiCount,
  exporting,
  onOpenAudit,
  onExport,
}: ExportBarProps) {
  return (
    <footer className="panel export-bar">
      <div className="export-info">
        {pendingManual > 0 ? (
          <span className="badge status-manual">
            仍有 {pendingManual} 条需人工确认
          </span>
        ) : (
          <span className="badge status-pass">无待确认项</span>
        )}
        <span className="muted">报告将包含逐条结论、证据与完整审计记录。</span>
        {mockAiCount > 0 && (
          <span className="badge badge-mock">AI 模拟结果不入报告</span>
        )}
      </div>
      <div className="export-actions">
        <button
          type="button"
          className="button button-ghost"
          onClick={onOpenAudit}
        >
          查看审计{auditCount > 0 ? `（${auditCount}）` : ""}
        </button>
        <button
          type="button"
          className="button button-secondary"
          disabled={exporting !== null}
          onClick={() => onExport("markdown")}
        >
          {exporting === "markdown" ? "导出中…" : "导出 Markdown"}
        </button>
        <button
          type="button"
          className="button button-primary"
          disabled={exporting !== null}
          onClick={() => onExport("json")}
        >
          {exporting === "json" ? "导出中…" : "导出 JSON"}
        </button>
      </div>
    </footer>
  );
}
