import { useEffect } from "react";

import type { AuditEntry } from "../types";
import { formatDateTime, statusLabel } from "../utils";

interface AuditDrawerProps {
  open: boolean;
  loading: boolean;
  error: string | null;
  audit: AuditEntry[];
  ruleNames: Record<string, string>;
  onClose: () => void;
  onRefresh: () => void;
}

export function AuditDrawer({
  open,
  loading,
  error,
  audit,
  ruleNames,
  onClose,
  onRefresh,
}: AuditDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const entries = [...audit].sort((a, b) => b.seq - a.seq);

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-head">
          <div>
            <h2 id="audit-title">审计记录</h2>
            <p className="muted">共 {audit.length} 条人工修改，按时间倒序。</p>
          </div>
          <div className="drawer-actions">
            <button
              type="button"
              className="button button-ghost"
              onClick={onRefresh}
              disabled={loading}
            >
              {loading ? "刷新中…" : "刷新"}
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </header>

        {error && (
          <div className="drawer-error" role="alert">
            {error}
          </div>
        )}

        {entries.length === 0 ? (
          <p className="drawer-empty">暂无人工修改记录。</p>
        ) : (
          <ul className="audit-list">
            {entries.map((entry) => (
              <li className="audit-item" key={`${entry.seq}-${entry.rule_id}`}>
                <div className="audit-item-head">
                  <strong>
                    {ruleNames[entry.rule_id] ?? entry.rule_id}
                  </strong>
                  <span className="audit-seq">#{entry.seq}</span>
                </div>
                <div className="audit-change">
                  <span className={`badge status-${entry.old_status}`}>
                    {statusLabel(entry.old_status)}
                  </span>
                  <span aria-hidden="true">→</span>
                  <span className={`badge status-${entry.new_status}`}>
                    {statusLabel(entry.new_status)}
                  </span>
                </div>
                <div className="audit-meta">
                  {entry.reviewer} · {formatDateTime(entry.timestamp)}
                </div>
                {entry.note && (
                  <div className="audit-note">备注：{entry.note}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
