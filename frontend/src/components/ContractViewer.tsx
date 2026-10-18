import { useEffect, useMemo } from "react";

import { buildSegments } from "../offsets";
import type { Evidence } from "../types";

export interface EvidenceTarget {
  ruleId: string;
  index: number;
}

interface ContractViewerProps {
  text: string;
  filename: string;
  activeRuleId: string | null;
  evidences: Evidence[];
  evidenceTarget: EvidenceTarget | null;
}

export function ContractViewer({
  text,
  filename,
  activeRuleId,
  evidences,
  evidenceTarget,
}: ContractViewerProps) {
  const segments = useMemo(
    () => buildSegments(text, evidences),
    [text, evidences],
  );

  useEffect(() => {
    if (!evidenceTarget) {
      return;
    }
    const element = document.getElementById(
      `ev-${evidenceTarget.ruleId}-${evidenceTarget.index}`,
    );
    if (!element) {
      return;
    }

    const panel = element.closest<HTMLElement>(".viewer-panel");
    if (panel) {
      const panelRect = panel.getBoundingClientRect();
      if (panelRect.top < 0 || panelRect.bottom > window.innerHeight) {
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    const container = element.closest<HTMLElement>(".contract-text");
    if (container) {
      const markRect = element.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      if (
        markRect.top < containerRect.top ||
        markRect.bottom > containerRect.bottom
      ) {
        container.scrollTo({
          top:
            container.scrollTop +
            (markRect.top - containerRect.top) -
            container.clientHeight / 2 +
            markRect.height / 2,
          behavior: "smooth",
        });
      }
    } else {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    element.setAttribute("tabindex", "-1");
    element.focus({ preventScroll: true });
    element.classList.remove("flash");
    void element.offsetWidth;
    element.classList.add("flash");
    const timer = window.setTimeout(
      () => element.classList.remove("flash"),
      1200,
    );
    return () => window.clearTimeout(timer);
  }, [evidenceTarget]);

  return (
    <section className="panel viewer-panel">
      <div className="panel-head">
        <h2>合同原文</h2>
        <span className="muted">{filename}</span>
      </div>
      <pre className="contract-text">
        {segments.map((segment, index) =>
          segment.evidenceIndex === null || activeRuleId === null ? (
            <span key={index}>{segment.text}</span>
          ) : (
            <mark
              key={index}
              id={`ev-${activeRuleId}-${segment.evidenceIndex}`}
              data-start={segment.start}
              className="evidence-mark"
            >
              {segment.text}
            </mark>
          ),
        )}
      </pre>
    </section>
  );
}
