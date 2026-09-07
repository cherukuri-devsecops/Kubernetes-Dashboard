import { API_BASE_URL, apiFetch } from "@/api/client";
import { AUTH_TOKEN_KEY } from "@/services/auth";

/** Loki stores raw lines with no level label, so the UI classifies each line
 * itself; this is the vocabulary it classifies into. */
export type LogLevel = "debug" | "info" | "warn" | "error";

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

export type PodLogStreamParams = {
  namespace: string;
  pod: string;
  container?: string;
  tailLines?: number;
  onLine: (line: string) => void;
  onError: (message: string) => void;
  onClose?: () => void;
  signal: AbortSignal;
};

/** Tails a pod's logs straight from the Kubernetes API (`kubectl logs -f`).
 *
 * Read with fetch rather than EventSource: EventSource cannot send the
 * Authorization header, and the endpoint requires a bearer token. */
export async function streamPodLogs({
  namespace,
  pod,
  container,
  tailLines,
  onLine,
  onError,
  onClose,
  signal,
}: PodLogStreamParams): Promise<void> {
  const params = new URLSearchParams({ namespace, pod });
  if (container) params.set("container", container);
  if (tailLines) params.set("tailLines", String(tailLines));

  const token = window.localStorage.getItem(AUTH_TOKEN_KEY);

  try {
    const response = await fetch(`${API_BASE_URL}/api/logs/stream?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal,
    });

    if (!response.ok || !response.body) {
      let detail = response.statusText;
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail;
      } catch {
        // Non-JSON error body; the status text is the best we have.
      }
      onError(detail || `Stream failed (${response.status})`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line; a partial tail stays buffered.
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const event of events) {
        for (const eventLine of event.split("\n")) {
          if (eventLine.startsWith("data:")) {
            onLine(eventLine.slice(5).replace(/^ /, ""));
          }
        }
      }
    }
    onClose?.();
  } catch (exc) {
    // An abort is the caller stopping the tail on purpose, not a failure.
    if (signal.aborted) return;
    onError(exc instanceof Error ? exc.message : "Log stream failed");
  }
}
