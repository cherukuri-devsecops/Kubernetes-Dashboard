import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, Check, CircleCheck, Info, ShieldAlert, TriangleAlert } from "lucide-react";
import clsx from "clsx";

import { AlertStatusBadge, SeverityBadge } from "@/components/common/badges";
import { StatTile } from "@/components/cards/StatTile";
import { formatRelativeTime, generateAlerts, type AlertItem, type AlertSeverity, type AlertStatus } from "@/utils/mockData";

const SEVERITIES: AlertSeverity[] = ["critical", "warning", "info"];
type ViewTab = "active" | "history";

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>(() => generateAlerts());
  const [severityFilter, setSeverityFilter] = useState<Set<AlertSeverity>>(new Set(SEVERITIES));
  const [tab, setTab] = useState<ViewTab>("active");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const byTab = useMemo(
    () => alerts.filter((alert) => (tab === "active" ? alert.status !== "resolved" : alert.status === "resolved")),
    [alerts, tab],
  );

  const filtered = useMemo(
    () => byTab.filter((alert) => severityFilter.has(alert.severity)),
    [byTab, severityFilter],
  );

  const selected = filtered.find((alert) => alert.id === selectedId) ?? filtered[0] ?? null;

  const counts = useMemo(
    () => ({
      total: alerts.length,
      critical: alerts.filter((a) => a.severity === "critical" && a.status !== "resolved").length,
      warning: alerts.filter((a) => a.severity === "warning" && a.status !== "resolved").length,
      info: alerts.filter((a) => a.severity === "info" && a.status !== "resolved").length,
      resolved: alerts.filter((a) => a.status === "resolved").length,
    }),
    [alerts],
  );

  function toggleSeverity(severity: AlertSeverity) {
    setSeverityFilter((current) => {
      const next = new Set(current);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  }

  function acknowledge(id: string) {
    setAlerts((current) => current.map((alert) => (alert.id === id ? { ...alert, status: "acknowledged" } : alert)));
  }

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div>
        <p className="text-sm text-brand-400">Alerts</p>
        <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Alert rules</h2>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Total Alerts" value={counts.total} icon={Bell} tone="neutral" />
        <StatTile label="Critical" value={counts.critical} icon={ShieldAlert} tone={counts.critical > 0 ? "red" : "green"} />
        <StatTile label="Warning" value={counts.warning} icon={TriangleAlert} tone={counts.warning > 0 ? "amber" : "green"} />
        <StatTile label="Info" value={counts.info} icon={Info} tone="blue" />
        <StatTile label="Resolved" value={counts.resolved} icon={CircleCheck} tone="green" />
      </section>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
        <div className="flex items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
          {([
            { key: "active", label: "Active Alerts" },
            { key: "history", label: "Alert History" },
          ] as { key: ViewTab; label: string }[]).map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setTab(option.key)}
              className={clsx(
                "h-8 rounded px-3 text-sm transition",
                tab === option.key
                  ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                  : "text-content-muted hover:text-content-primary",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-content-muted">Severity</span>
          {SEVERITIES.map((severity) => (
            <button
              key={severity}
              type="button"
              onClick={() => toggleSeverity(severity)}
              className={clsx(
                "rounded-full border px-2.5 py-1 text-xs font-medium capitalize transition",
                severityFilter.has(severity)
                  ? "border-brand/40 bg-brand/10 text-brand-400"
                  : "border-line text-content-muted hover:text-content-primary",
              )}
            >
              {severity}
            </button>
          ))}
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-lg border border-line bg-surface">
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-content-muted">No alerts match the current filters.</p>
          ) : (
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
                  <th className="py-2 pl-4 pr-2 font-medium">Severity</th>
                  <th className="py-2 pr-2 font-medium">Alert Name</th>
                  <th className="py-2 pr-2 font-medium">Affected</th>
                  <th className="py-2 pr-2 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Since</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((alert) => (
                  <tr
                    key={alert.id}
                    onClick={() => setSelectedId(alert.id)}
                    className={clsx("cursor-pointer transition hover:bg-surface-hover", selected?.id === alert.id && "bg-surface-hover")}
                  >
                    <td className="py-2.5 pl-4 pr-2">
                      <SeverityBadge severity={alert.severity} />
                    </td>
                    <td className="py-2.5 pr-2 text-content-primary">{alert.name}</td>
                    <td className="py-2.5 pr-2 text-content-secondary">{alert.resource}</td>
                    <td className="py-2.5 pr-2">
                      <AlertStatusBadge status={alert.status} />
                    </td>
                    <td className="py-2.5 pr-4 text-content-muted">{formatRelativeTime(alert.startedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="rounded-lg border border-line bg-surface p-4">
          <h3 className="mb-3 text-sm font-medium text-content-primary">Alert Detail</h3>
          {selected ? (
            <div className="space-y-3 text-xs">
              <div className="flex items-center gap-2">
                <SeverityBadge severity={selected.severity} />
                <AlertStatusBadge status={selected.status} />
              </div>
              <p className="text-sm font-medium text-content-primary">{selected.name}</p>
              <div>
                <p className="text-content-muted">Affected</p>
                <p className="text-content-primary">{selected.resource}</p>
              </div>
              <div>
                <p className="text-content-muted">Since</p>
                <p className="text-content-primary">{formatRelativeTime(selected.startedAt)}</p>
              </div>
              <div>
                <p className="mb-1 text-content-muted">Description</p>
                <p className="rounded-md bg-surface-hover/60 p-2 text-content-secondary">{selected.message}</p>
              </div>
              <div className="flex gap-2 pt-1">
                {selected.status === "firing" ? (
                  <button
                    type="button"
                    onClick={() => acknowledge(selected.id)}
                    className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                  >
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    Acknowledge
                  </button>
                ) : null}
                <Link
                  to="/logs"
                  className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                >
                  View in Logs
                </Link>
              </div>
            </div>
          ) : (
            <p className="text-xs text-content-muted">Select an alert to see its details.</p>
          )}
        </div>
      </section>
    </div>
  );
}
