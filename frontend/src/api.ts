import type {
  AnnotationResponse,
  AnnotationStatus,
  HealthResponse,
  ReportFormat,
  ReportResponse,
  ReviewDetail,
  ReviewResponse,
  SampleDetail,
  SampleInfo,
} from "./types";

const REQUEST_TIMEOUT_MS = 30_000;
// LLM 超时 20s 且 SDK 允许一次重试，审查请求需要更长的等待时间。
const REVIEW_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface SampleListResponse {
  samples: SampleInfo[];
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
    const payload = (await response.json().catch(() => null)) as unknown;

    if (!response.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? String((payload as { detail: unknown }).detail)
          : `请求失败（HTTP ${response.status}）`;
      throw new ApiError(detail, response.status);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("请求超时，请稍后重试");
    }
    throw new ApiError("网络错误，请确认后端服务已启动");
  } finally {
    window.clearTimeout(timeout);
  }
}

export function fetchSamples(): Promise<SampleInfo[]> {
  return request<SampleListResponse>("/samples").then(
    (payload) => payload.samples,
  );
}

export function fetchSample(sampleId: string): Promise<SampleDetail> {
  return request<SampleDetail>(`/samples/${encodeURIComponent(sampleId)}`);
}

export interface ReviewOptions {
  llmEnabled: boolean;
  apiKey?: string;
  model?: string;
}

export function createReview(
  text: string,
  filename: string,
  options?: ReviewOptions,
): Promise<ReviewResponse> {
  const headers: Record<string, string> = {};
  if (options) {
    headers["X-LLM-Enabled"] = options.llmEnabled ? "true" : "false";
    if (options.llmEnabled && options.apiKey?.trim()) {
      headers["X-Anthropic-Api-Key"] = options.apiKey.trim();
    }
    if (options.model?.trim()) {
      headers["X-Anthropic-Model"] = options.model.trim();
    }
  }
  return request<ReviewResponse>(
    "/review",
    {
      method: "POST",
      headers,
      body: JSON.stringify({ text, filename }),
    },
    REVIEW_TIMEOUT_MS,
  );
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export interface CreateAnnotationInput {
  reviewId: string;
  ruleId: string;
  reviewer: string;
  status: AnnotationStatus;
  note: string | null;
}

export function createAnnotation(
  input: CreateAnnotationInput,
): Promise<AnnotationResponse> {
  return request<AnnotationResponse>("/annotations", {
    method: "POST",
    body: JSON.stringify({
      review_id: input.reviewId,
      rule_id: input.ruleId,
      reviewer: input.reviewer,
      status: input.status,
      note: input.note,
    }),
  });
}

export function fetchReviewDetail(reviewId: string): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/reviews/${encodeURIComponent(reviewId)}`);
}

export function createReport(
  reviewId: string,
  format: ReportFormat,
): Promise<ReportResponse> {
  return request<ReportResponse>("/report", {
    method: "POST",
    body: JSON.stringify({ review_id: reviewId, format }),
  });
}
