import { useState } from "react";
import type { ChangeEvent } from "react";

import { MAX_FILE_BYTES, MAX_TEXT_CHARS } from "../constants";
import type { SampleInfo } from "../types";
import { formatCount } from "../utils";

interface UploadPanelProps {
  text: string;
  filename: string;
  charCount: number;
  loading: boolean;
  samples: SampleInfo[];
  onTextChange: (value: string) => void;
  onTextLoaded: (text: string, filename: string) => void;
  onSample: (sampleId: string) => Promise<void>;
  onReview: () => void;
  onError: (message: string) => void;
}

export function UploadPanel({
  text,
  filename,
  charCount,
  loading,
  samples,
  onTextChange,
  onTextLoaded,
  onSample,
  onReview,
  onError,
}: UploadPanelProps) {
  const [sampleLoadingId, setSampleLoadingId] = useState<string | null>(null);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    if (!/\.(txt|md)$/i.test(file.name)) {
      onError("仅支持 .txt 或 .md 文件");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      onError("文件超过 512 KB，请精简后再上传");
      return;
    }
    try {
      const content = await file.text();
      onTextLoaded(content, file.name);
    } catch {
      onError("文件读取失败，请重试");
    }
  }

  async function handleSample(sampleId: string) {
    setSampleLoadingId(sampleId);
    try {
      await onSample(sampleId);
    } finally {
      setSampleLoadingId(null);
    }
  }

  const overLimit = charCount > MAX_TEXT_CHARS;
  const disabled = loading || !text.trim() || overLimit;

  return (
    <section className="panel upload-panel">
      <div className="panel-head">
        <div>
          <h2>上传合同</h2>
          <p className="muted">
            支持 .txt / .md 文件（不超过 512 KB），或直接粘贴文本。
          </p>
        </div>
        <span className="muted">当前文件：{filename}</span>
      </div>

      <div className="upload-toolbar">
        <label className="button button-secondary file-button">
          选择文件
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={(event) => void handleFile(event)}
          />
        </label>
        <div className="sample-group">
          <span className="muted">样例：</span>
          {samples.map((sample) => (
            <button
              key={sample.id}
              type="button"
              className="button button-ghost"
              disabled={sampleLoadingId !== null || loading}
              onClick={() => void handleSample(sample.id)}
            >
              {sampleLoadingId === sample.id
                ? "加载中…"
                : sample.description}
            </button>
          ))}
          {samples.length === 0 && (
            <span className="muted">样例加载中…</span>
          )}
        </div>
      </div>

      <textarea
        className="text-input"
        value={text}
        rows={12}
        placeholder="在此粘贴合同文本…"
        onChange={(event) => onTextChange(event.target.value)}
      />

      <div className="upload-footer">
        <span className={overLimit ? "counter over-limit" : "counter"}>
          {formatCount(charCount)} / {formatCount(MAX_TEXT_CHARS)} 字符
          {overLimit ? "，已超出上限" : ""}
        </span>
        <button
          type="button"
          className="button button-primary"
          disabled={disabled}
          onClick={onReview}
        >
          {loading ? "审查中…" : "开始审查"}
        </button>
      </div>
    </section>
  );
}
