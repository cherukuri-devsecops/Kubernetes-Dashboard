import { apiFetch } from "@/api/client";
import { parseDate } from "@/utils/format";

export type AlertSeverity = "critical" | "warning" | "info";
/** Prometheus alert states. "resolved" is not one of them — an alert that stops
 * matching simply disappears — so the UI reads history from the rule list. */
export type AlertState = "firing" | "pending";

type AlertResponse = {
  id: string;
  name: string;
  severity: AlertSeverity;
  state: AlertState;
  resource: string;
  summary: string;
  message: string;
  runbookUrl: string;
  startedAt: string | null;
  value: string | null;
  labels: Record<string, string>;
};

export type AlertItem = Omit<AlertResponse, "startedAt"> & { startedAt: Date };

export type AlertRule = {
  name: string;
  group: string;
  severity: AlertSeverity;
  state: "firing" | "pending" | "inactive";
  query: string;
  durationSeconds: number;
  summary: string;
  description: string;
  activeCount: number;
  health: string;
  lastError: string;
};

export type AlertsSnapshot = {
  alerts: AlertItem[];
  rules: AlertRule[];
  ruleCount: number;
  firingCount: number;
  pendingCount: number;
};

type AlertsResponse = Omit<AlertsSnapshot, "alerts"> & { alerts: AlertResponse[] };

export async function fetchAlerts(): Promise<AlertsSnapshot> {
  const body = await apiFetch<AlertsResponse>("/api/alerts");
  return {
    ...body,
    alerts: body.alerts.map((alert) => ({ ...alert, startedAt: parseDate(alert.startedAt) })),
  };
}
