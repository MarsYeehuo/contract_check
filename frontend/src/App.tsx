import { useEffect, useMemo, useState } from "react";

import {
  createAnnotation,
  createReport,
  createReview,
  fetchHealth,
  fetchReviewDetail,
  fetchSample,
  fetchSamples,
} from "./api";
import { AiSettingsDialog } from "./components/AiSettingsDialog";
import { AuditDrawer } from "./components/AuditDrawer";
import {
  ContractViewer,
  type EvidenceTarget,
} from "./components/ContractViewer";
import { ExportBar } from "./components/ExportBar";
import { Header } from "./components/Header";
import { MockAiBanner } from "./components/MockAiBanner";
import { RuleCard } from "./components/RuleCard";
import { SummaryBar } from "./components/SummaryBar";
import { UploadPanel } from "./components/UploadPanel";
import {
  DEFAULT_FILENAME,
  DEFAULT_REVIEWER,
  MAX_TEXT_CHARS,
} from "./constants";
import { buildMockAssessments } from "./mockLlm";
import type {
  AIInfo,
  Annotation,
  AnnotationStatus,
  AuditEntry,
  EffectiveStatus,
  ReportFormat,
  ReviewResponse,
  RuleResult,
  SampleInfo,
} from "./types";
import { downloadTextFile, formatCount } from "./utils";
import "./App.css";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请重试";
}

function resolveEffectiveStatus(
  result: RuleResult,
  annotation: Annotation | undefined,
): EffectiveStatus {
  return annotation?.status ?? result.status;
}

function App() {
  const [text, setText] = useState("");
  const [filename, setFilename] = useState(DEFAULT_FILENAME);
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [reviewedText, setReviewedText] = useState("");
  const [annotations, setAnnotations] = useState<Record<string, Annotation>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [activeRuleId, setActiveRuleId] = useState<string | null>(null);
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(
    null,
  );
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<ReportFormat | null>(null);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [reviewer, setReviewer] = useState(
    () => localStorage.getItem("reviewer") ?? DEFAULT_REVIEWER,
  );
  const [aiEnabled, setAiEnabled] = useState(
    () => localStorage.getItem("aiEnabled") !== "false",
  );
  const [apiKey, setApiKey] = useState(
    () => sessionStorage.getItem("aiApiKey") ?? "",
  );
  const [aiModel, setAiModel] = useState(
    () => localStorage.getItem("aiModel") ?? "",
  );
  const [aiSettingsOpen, setAiSettingsOpen] = useState(false);
  const [serverLlmConfigured, setServerLlmConfigured] = useState<
    boolean | null
  >(null);
  const [mockAi, setMockAi] = useState<Record<string, AIInfo>>({});
  const [loading, setLoading] = useState(false);
  const [savingRuleId, setSavingRuleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [toast, setToast] = useState<string | null>(null);

  const charCount = useMemo(() => Array.from(text).length, [text]);

  useEffect(() => {
    localStorage.setItem("reviewer", reviewer);
  }, [reviewer]);

  useEffect(() => {
    localStorage.setItem("aiEnabled", String(aiEnabled));
  }, [aiEnabled]);

  useEffect(() => {
    localStorage.setItem("aiModel", aiModel);
  }, [aiModel]);

  useEffect(() => {
    if (apiKey) {
      sessionStorage.setItem("aiApiKey", apiKey);
    } else {
      sessionStorage.removeItem("aiApiKey");
    }
  }, [apiKey]);

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((health) => {
        if (!cancelled) {
          setServerLlmConfigured(health.llm_configured);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setServerLlmConfigured(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleOpenAiSettings() {
    setAiSettingsOpen(true);
    try {
      const health = await fetchHealth();
      setServerLlmConfigured(health.llm_configured);
    } catch {
      setServerLlmConfigured(null);
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetchSamples()
      .then((items) => {
        if (!cancelled) {
          setSamples(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSamples([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timer = window.setTimeout(() => setToast(null), 2500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function handleReview() {
    if (!text.trim()) {
      setError("请先输入或加载合同文本");
      setRetryable(false);
      return;
    }
    if (charCount > MAX_TEXT_CHARS) {
      setError(`合同文本超过 ${formatCount(MAX_TEXT_CHARS)} 字符，请精简后再审查`);
      setRetryable(false);
      return;
    }

    setLoading(true);
    setError(null);
    setRetryable(false);
    try {
      const result = await createReview(text, filename, {
        llmEnabled: aiEnabled,
        apiKey: apiKey.trim() || undefined,
        model: aiModel.trim() || undefined,
      });
      setReview(result);
      setReviewedText(text);
      setAnnotations({});
      setAudit([]);
      setAuditOpen(false);
      setAuditError(null);
      setEvidenceTarget(null);
      setMockAi(
        result.llm.status === "no_key"
          ? buildMockAssessments(result.results, text)
          : {},
      );
      const preferred =
        result.results.find((item) => item.status === "risk") ??
        result.results.find((item) => item.status === "manual") ??
        result.results[0] ??
        null;
      setActiveRuleId(preferred?.rule_id ?? null);
      setPanelOpen(false);
    } catch (caught) {
      setError(errorMessage(caught));
      setRetryable(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleSample(sampleId: string) {
    setError(null);
    setRetryable(false);
    try {
      const sample = await fetchSample(sampleId);
      setText(sample.text);
      setFilename(sample.filename);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function handleAnnotate(
    ruleId: string,
    status: AnnotationStatus,
    note: string,
  ) {
    if (!review) {
      return;
    }
    const name = reviewer.trim();
    if (!name) {
      setError("请先填写审核人");
      setRetryable(false);
      return;
    }

    setSavingRuleId(ruleId);
    setError(null);
    try {
      const response = await createAnnotation({
        reviewId: review.review_id,
        ruleId,
        reviewer: name,
        status,
        note: note || null,
      });
      setAnnotations((current) => ({
        ...current,
        [ruleId]: response.annotation,
      }));
      setAudit((current) =>
        [...current.filter((entry) => entry.seq !== response.audit_entry.seq), response.audit_entry].sort(
          (a, b) => a.seq - b.seq,
        ),
      );
      setToast("结论已保存，已记录审计");
    } catch (caught) {
      setError(errorMessage(caught));
      setRetryable(false);
    } finally {
      setSavingRuleId(null);
    }
  }

  async function refreshAudit(reviewId: string) {
    setAuditLoading(true);
    setAuditError(null);
    try {
      const detail = await fetchReviewDetail(reviewId);
      setAudit(detail.audit);
      setAnnotations(
        Object.fromEntries(
          detail.annotations.map((item) => [item.rule_id, item]),
        ),
      );
    } catch (caught) {
      setAuditError(errorMessage(caught));
    } finally {
      setAuditLoading(false);
    }
  }

  function handleOpenAudit() {
    setAuditOpen(true);
    if (review) {
      void refreshAudit(review.review_id);
    }
  }

  function handleEvidenceSelect(ruleId: string, index: number) {
    setActiveRuleId(ruleId);
    setEvidenceTarget({ ruleId, index });
  }

  async function handleExport(format: ReportFormat) {
    if (!review) {
      return;
    }
    if (
      pendingManual > 0 &&
      !window.confirm(`仍有 ${pendingManual} 条需人工确认，是否继续导出？`)
    ) {
      return;
    }

    setExporting(format);
    setError(null);
    setRetryable(false);
    try {
      const report = await createReport(review.review_id, format);
      downloadTextFile(report.content, report.mime, report.filename);
      setToast(`已导出 ${format === "json" ? "JSON" : "Markdown"} 报告`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setExporting(null);
    }
  }

  const showPanel = panelOpen || review === null;
  const annotatedCount = Object.keys(annotations).length;
  const pendingManual = review
    ? review.results.filter(
        (result) =>
          resolveEffectiveStatus(result, annotations[result.rule_id]) ===
          "manual",
      ).length
    : 0;
  const ruleNames = useMemo(
    () =>
      Object.fromEntries(
        (review?.results ?? []).map((result) => [result.rule_id, result.name]),
      ),
    [review],
  );
  const activeEvidences = useMemo(
    () =>
      review?.results.find((result) => result.rule_id === activeRuleId)
        ?.evidence ?? [],
    [review, activeRuleId],
  );
  const mockAiCount = Object.keys(mockAi).length;

  return (
    <div className="app-shell">
      <Header
        reviewer={reviewer}
        onReviewerChange={setReviewer}
        onOpenAiSettings={() => void handleOpenAiSettings()}
      />

      {mockAiCount > 0 && <MockAiBanner />}

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <div className="error-actions">
            {retryable && (
              <button
                type="button"
                className="button button-secondary"
                onClick={() => void handleReview()}
              >
                重试
              </button>
            )}
            <button
              type="button"
              className="button button-ghost"
              onClick={() => setError(null)}
            >
              关闭
            </button>
          </div>
        </div>
      )}

      {showPanel ? (
        <UploadPanel
          text={text}
          filename={filename}
          charCount={charCount}
          loading={loading}
          samples={samples}
          onTextChange={setText}
          onTextLoaded={(content, name) => {
            setText(content);
            setFilename(name);
          }}
          onSample={handleSample}
          onReview={() => void handleReview()}
          onError={(message) => {
            setError(message);
            setRetryable(false);
          }}
        />
      ) : (
        <div className="panel collapsed-bar">
          <div>
            <strong>{review?.filename}</strong>
            <span className="muted">
              {" "}
              · {formatCount(Array.from(reviewedText).length)} 字符
            </span>
          </div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setPanelOpen(true)}
          >
            修改文本 / 重新审查
          </button>
        </div>
      )}

      {review ? (
        <main className="workspace">
          <ContractViewer
            text={reviewedText}
            filename={review.filename}
            activeRuleId={activeRuleId}
            evidences={activeEvidences}
            evidenceTarget={evidenceTarget}
          />
          <div className="results-column">
            <SummaryBar
              summary={review.summary}
              annotatedCount={annotatedCount}
              rulesetVersion={review.ruleset_version}
              llmStatus={review.llm.status}
              mockAiCount={mockAiCount}
            />
            <div className="rule-list">
              {review.results.map((result) => (
                <RuleCard
                  key={`${review.review_id}-${result.rule_id}`}
                  result={result}
                  annotation={annotations[result.rule_id]}
                  effectiveStatus={resolveEffectiveStatus(
                    result,
                    annotations[result.rule_id],
                  )}
                  ai={result.ai ?? mockAi[result.rule_id] ?? null}
                  active={activeRuleId === result.rule_id}
                  saving={savingRuleId === result.rule_id}
                  onSelect={() => {
                    setActiveRuleId(result.rule_id);
                    setEvidenceTarget(null);
                  }}
                  onEvidenceSelect={(index) =>
                    handleEvidenceSelect(result.rule_id, index)
                  }
                  onAnnotate={(status, note) =>
                    void handleAnnotate(result.rule_id, status, note)
                  }
                />
              ))}
            </div>
          </div>
        </main>
      ) : (
        <section className="empty-state">
          <h2>准备开始审查</h2>
          <p>加载一份样例，或上传/粘贴合同文本，然后点击「开始审查」。</p>
          <p className="muted">
            审查结果、命中证据和人工复核入口会显示在这里。
          </p>
        </section>
      )}

      {review && (
        <ExportBar
          auditCount={audit.length}
          pendingManual={pendingManual}
          mockAiCount={mockAiCount}
          exporting={exporting}
          onOpenAudit={handleOpenAudit}
          onExport={(format) => void handleExport(format)}
        />
      )}

      <AuditDrawer
        open={auditOpen}
        loading={auditLoading}
        error={auditError}
        audit={audit}
        ruleNames={ruleNames}
        onClose={() => setAuditOpen(false)}
        onRefresh={() => {
          if (review) {
            void refreshAudit(review.review_id);
          }
        }}
      />

      <AiSettingsDialog
        open={aiSettingsOpen}
        enabled={aiEnabled}
        apiKey={apiKey}
        model={aiModel}
        serverConfigured={serverLlmConfigured}
        onEnabledChange={setAiEnabled}
        onApiKeyChange={setApiKey}
        onModelChange={setAiModel}
        onClose={() => setAiSettingsOpen(false)}
      />

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

export default App;
