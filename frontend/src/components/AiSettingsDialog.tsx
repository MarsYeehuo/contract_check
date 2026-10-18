import { useEffect } from "react";

interface AiSettingsDialogProps {
  open: boolean;
  enabled: boolean;
  apiKey: string;
  model: string;
  serverConfigured: boolean | null;
  onEnabledChange: (value: boolean) => void;
  onApiKeyChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onClose: () => void;
}

export function AiSettingsDialog({
  open,
  enabled,
  apiKey,
  model,
  serverConfigured,
  onEnabledChange,
  onApiKeyChange,
  onModelChange,
  onClose,
}: AiSettingsDialogProps) {
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

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <div>
            <h2 id="ai-settings-title">AI 兜底设置</h2>
            <p className="muted">
              AI 建议仅供参考，不改变引擎结论，也不会替代人工复核。
            </p>
          </div>
          <button
            type="button"
            className="button button-ghost"
            onClick={onClose}
          >
            关闭
          </button>
        </header>

        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => onEnabledChange(event.target.checked)}
          />
          <span>启用 AI 兜底（仅对未命中的规则）</span>
        </label>

        <label className="field">
          <span>Anthropic API Key</span>
          <input
            type="password"
            value={apiKey}
            autoComplete="off"
            placeholder={
              serverConfigured
                ? "服务端已配置 Key，可留空"
                : "sk-…（仅保存在本标签页）"
            }
            onChange={(event) => onApiKeyChange(event.target.value)}
          />
          <span className="field-hint">
            仅保存在本标签页的 sessionStorage，关闭标签页即清除；不会写入审计或报告。
          </span>
        </label>

        <label className="field">
          <span>模型（可选）</span>
          <input
            value={model}
            maxLength={100}
            placeholder="留空使用服务端配置，例如 claude-haiku-4-5-20251001"
            onChange={(event) => onModelChange(event.target.value)}
          />
        </label>

        <div className="ai-server-status">
          <span
            className={
              serverConfigured
                ? "badge status-pass"
                : "badge status-manual"
            }
          >
            {serverConfigured === null
              ? "服务端状态未知"
              : serverConfigured
                ? "服务端已配置 Key"
                : "服务端未配置 Key"}
          </span>
          {!serverConfigured && (
            <span className="muted">
              未填写 Key 时，前端会本地模拟 AI 建议并明确标注。
            </span>
          )}
        </div>

        <p className="modal-note">
          公网部署时请勿在浏览器中输入真实 Key，应使用服务端环境变量与
          HTTPS。
        </p>
      </section>
    </div>
  );
}
