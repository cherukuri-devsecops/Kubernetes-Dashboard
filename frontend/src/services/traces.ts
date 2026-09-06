import { apiFetch } from "@/api/client";

export type SpanStatus = "ok" | "error";

export type TraceSummary = {
  id: string;
  rootService: string;
  operation: string;
  durationMs: number;
  startUnixNano: number;
  status: SpanStatus;
  spanCount: number;
  services: string[];
};

export type TraceSpan = {
  id: string;
  parentId: string | null;
  name: string;
  service: string;
  kind: string;
  startUnixNano: number;
  startOffsetMs: number;
  durationMs: number;
  status: SpanStatus;
  attributes: Record<string, string | number | boolean>;
};

export type Trace = {
  id: string;
  rootService: string;
  operation: string;
  durationMs: number;
  status: SpanStatus;
  startUnixNano: number;
  spans: TraceSpan[];
};

export type TraceSearchParams = {
  limit?: number;
  rangeMinutes?: number;
  service?: string;
  minDurationMs?: number;
};

/** Tempo timestamps are nanoseconds; JS dates are milliseconds. */
export function traceStartedAt(trace: { startUnixNano: number }): Date {
  return new Date(trace.startUnixNano / 1_000_000);
}

export function fetchTraces({ limit, rangeMinutes, service, minDurationMs }: TraceSearchParams = {}) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (rangeMinutes) params.set("rangeMinutes", String(rangeMinutes));
  if (service) params.set("service", service);
  if (minDurationMs) params.set("minDurationMs", String(minDurationMs));
  return apiFetch<TraceSummary[]>(`/api/traces?${params.toString()}`);
}

export const fetchTrace = (traceId: string) => apiFetch<Trace>(`/api/traces/${encodeURIComponent(traceId)}`);

export const fetchTraceServices = () => apiFetch<string[]>("/api/traces/services");
