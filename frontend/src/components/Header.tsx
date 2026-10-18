interface HeaderProps {
  reviewer: string;
  onReviewerChange: (value: string) => void;
  onOpenAiSettings: () => void;
}

export function Header({
  reviewer,
  onReviewerChange,
  onOpenAiSettings,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="brand">
        <h1>合同初审工作台</h1>
        <p className="subtitle">规则引擎自动审查 · 人工复核留痕</p>
      </div>
      <div className="header-actions">
        <label className="reviewer-field">
          <span>审核人</span>
          <input
            value={reviewer}
            maxLength={50}
            onChange={(event) => onReviewerChange(event.target.value)}
            placeholder="请输入审核人姓名"
          />
        </label>
        <button
          type="button"
          className="button button-ghost"
          onClick={onOpenAiSettings}
        >
          AI 设置
        </button>
      </div>
    </header>
  );
}
