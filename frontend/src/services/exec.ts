import { apiFetch, API_BASE_URL } from "@/api/client";
import { AUTH_TOKEN_KEY } from "@/services/auth";

export type ExecConfig = {
  enabled: boolean;
  allowedNamespaces: string[];
  shells: string[];
};

export const fetchExecConfig = () => apiFetch<ExecConfig>("/api/exec/config");

export type ExecSessionParams = {
  namespace: string;
  pod: string;
  container?: string;
  onOutput: (chunk: string) => void;
  onClose: (reason: string) => void;
};

export type ExecSession = {
  send: (data: string) => void;
  resize: (rows: number, cols: number) => void;
  close: () => void;
};

function socketUrl(path: string): string {
  // API_BASE_URL is normally empty (same origin, proxied by nginx), so build the
  // ws:// URL from the page's own origin and match its TLS.
  const base = API_BASE_URL || window.location.origin;
  const url = new URL(path, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** Opens an interactive shell in a pod.
 *
 * The token is passed as a WebSocket subprotocol because browsers cannot set an
 * Authorization header on a WebSocket — this keeps it out of the URL, and so out
 * of proxy and server access logs. */
export function openExecSession({
  namespace,
  pod,
  container,
  onOutput,
  onClose,
}: ExecSessionParams): ExecSession {
  const params = new URLSearchParams({ namespace, pod });
  if (container) params.set("container", container);

  const token = window.localStorage.getItem(AUTH_TOKEN_KEY) ?? "";
  const socket = new WebSocket(socketUrl(`/api/exec/pod?${params.toString()}`), ["bearer", token]);

  socket.onmessage = (event) => onOutput(String(event.data));
  socket.onerror = () => onClose("Connection failed");
  socket.onclose = (event) => onClose(event.reason || "Session ended");

  const sendJson = (payload: unknown) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
  };

  return {
    send: (data: string) => sendJson({ type: "stdin", data }),
    resize: (rows: number, cols: number) => sendJson({ type: "resize", rows, cols }),
    close: () => socket.close(),
  };
}
