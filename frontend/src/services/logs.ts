import { apiFetch } from "@/api/client";

export type LogEntry = {
  timestamp: number;
  namespace: string;
  pod: string;
  container: string;
  line: string;
};

export type LogSearchParams = {
  namespace?: string;
  pod?: string;
  container?: string;
  query?: string;
  rangeMinutes?: number;
  limit?: number;
};

export const searchLogs = ({ namespace, pod, container, query, rangeMinutes, limit }: LogSearchParams) => {
  const params = new URLSearchParams();
  if (namespace) params.set("namespace", namespace);
  if (pod) params.set("pod", pod);
  if (container) params.set("container", container);
  if (query) params.set("query", query);
  if (rangeMinutes) params.set("rangeMinutes", String(rangeMinutes));
  if (limit) params.set("limit", String(limit));

  return apiFetch<{ entries: LogEntry[] }>(`/api/logs/search?${params.toString()}`);
};
