import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, CircleCheck, Info, RefreshCw, ShieldAlert, TriangleAlert } from "lucide-react";
import clsx from "clsx";

import { AlertStateBadge, Pill, SeverityBadge } from "@/components/common/badges";
import { StatTile } from "@/components/cards/StatTile";
import { fetchAlerts, type AlertItem, type AlertRule, type AlertSeverity, type AlertsSnapshot } from "@/services/alerts";
import { formatRelativeTime } from "@/utils/format";

const SEVERITIES: AlertSeverity[] = ["critical", "warning", "info"];
const REFRESH_INTERVAL_MS = 15000;

type ViewTab = "active" | "rules";

const EMPTY: AlertsSnapshot = { alerts: [], rules: [], ruleCount: 0, firingCount: 0, pendingCount: 0 };

function formatFor(seconds: number): string {
  if (!seconds) return "immediately";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

export function AlertsPage() {
  const [snapshot, setSnapshot] = useState<AlertsSnapshot>(EMPTY);
  const [severityFilter, setSeverityFilter] = useState<Set<AlertSeverity>>(new Set(SEVERITIES));
  const [tab, setTab] = useState<ViewTab>("active");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const next = await fetchAlerts();
        if (cancelled) return;
        setSnapshot(next);
        setError(null);
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load alerts");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const { alerts, rules } = snapshot;

  const filteredAlerts = useMemo(
    () => alerts.filter((alert) => severityFilter.has(alert.severity)),
    [alerts, severityFilter],
  );

  const filteredRules = useMemo(
    () => rules.filter((rule) => severityFilter.has(rule.severity)),
    [rules, severityFilter],
  );

  const selected: AlertItem | null =
    filteredAlerts.find((alert) => alert.id === selectedId) ?? filteredAlerts[0] ?? null;

  const counts = useMemo(
    () => ({
      total: alerts.length,
      critical: alerts.filter((alert) => alert.severity === "critical").length,
      warning: alerts.filter((alert) => alert.severity === "warning").length,
      info: alerts.filter((alert) => alert.severity === "info").length,
      inactive: rules.filter((rule) => rule.state === "inactive").length,
    }),
    [alerts, rules],
  );

  function toggleSeverity(severity: AlertSeverity) {
    setSeverityFilter((current) => {
      const next = new Set(current);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  }

  const noRulesConfigured = !loading && !error && rules.length === 0;

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Alerts</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Alert rules</h2>
          <p className="mt-0.5 text-xs text-content-muted">
            Live from Prometheus — {snapshot.ruleCount} rule{snapshot.ruleCount === 1 ? "" : "s"} evaluated against the cluster.
          </p>
        </div>
        <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && "animate-spin")} aria-hidden="true" />
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      {noRulesConfigured ? (
        <p className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 px-3 py-2 text-xs text-signal-amber">
          Prometheus has no alerting rules loaded, so nothing can fire. Deploy the chart's alert-rules.yml to populate this page.
        </p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Active Alerts" value={counts.total} icon={Bell} tone="neutral" />
        <StatTile label="Critical" value={counts.critical} icon={ShieldAlert} tone={counts.critical > 0 ? "red" : "green"} />
        <StatTile label="Warning" value={counts.warning} icon={TriangleAlert} tone={counts.warning > 0 ? "amber" : "green"} />
        <StatTile label="Info" value={counts.info} icon={Info} tone="blue" />
        <StatTile label="Rules Quiet" value={counts.inactive} icon={CircleCheck} tone="green" />
      </section>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
        <div className="flex items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
          {([
            { key: "active", label: `Active (${alerts.length})` },
            { key: "rules", label: `Configured Rules (${rules.length})` },
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

      {tab === "active" ? (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="rounded-lg border border-line bg-surface">
            {filteredAlerts.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-content-muted">
                {loading ? "Loading alerts…" : "Nothing is firing right now."}
              </p>
            ) : (
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
                    <th className="py-2 pl-4 pr-2 font-medium">Severity</th>
                    <th className="py-2 pr-2 font-medium">Alert Name</th>
                    <th className="py-2 pr-2 font-medium">Affected</th>
                    <th className="py-2 pr-2 font-medium">State</th>
                    <th className="py-2 pr-4 font-medium">Since</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {filteredAlerts.map((alert) => (
                    <tr
                      key={alert.id}
                      onClick={() => setSelectedId(alert.id)}
                      className={clsx(
                        "cursor-pointer transition hover:bg-surface-hover",
                        selected?.id === alert.id && "bg-surface-hover",
                      )}
                    >
                      <td className="py-2.5 pl-4 pr-2">
                        <SeverityBadge severity={alert.severity} />
                      </td>
                      <td className="py-2.5 pr-2 text-content-primary">{alert.name}</td>
                      <td className="py-2.5 pr-2 text-content-secondary">{alert.resource}</td>
                      <td className="py-2.5 pr-2">
                        <AlertStateBadge state={alert.state} />
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
                  <AlertStateBadge state={selected.state} />
                </div>
                <p className="text-sm font-medium text-content-primary">{selected.name}</p>
                <div>
                  <p className="text-content-muted">Affected</p>
                  <p className="break-words text-content-primary">{selected.resource}</p>
                </div>
                <div>
                  <p className="text-content-muted">Since</p>
                  <p className="text-content-primary">{formatRelativeTime(selected.startedAt)}</p>
                </div>
                {selected.value ? (
                  <div>
                    <p className="text-content-muted">Value</p>
                    <p className="font-mono text-content-primary">{selected.value}</p>
                  </div>
                ) : null}
                <div>
                  <p className="mb-1 text-content-muted">Description</p>
                  <p className="rounded-md bg-surface-hover/60 p-2 text-content-secondary">{selected.message || "—"}</p>
                </div>
                <div>
                  <p className="mb-1 text-content-muted">Labels</p>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(selected.labels).map(([key, value]) => (
                      <Pill key={key} label={`${key}=${value}`} />
                    ))}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {selected.runbookUrl ? (
                    <a
                      href={selected.runbookUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                    >
                      Runbook
                    </a>
                  ) : null}
                  <Link
                    to={
                      selected.labels.namespace
                        ? `/logs?namespace=${encodeURIComponent(selected.labels.namespace)}`
                        : "/logs"
                    }
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
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          {filteredRules.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-content-muted">
              {loading ? "Loading rules…" : "No alerting rules are configured in Prometheus."}
            </p>
          ) : (
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
                  <th className="py-2 pl-4 pr-2 font-medium">Severity</th>
                  <th className="py-2 pr-2 font-medium">Rule</th>
                  <th className="py-2 pr-2 font-medium">Group</th>
                  <th className="py-2 pr-2 font-medium">State</th>
                  <th className="py-2 pr-2 font-medium">Active</th>
                  <th className="py-2 pr-2 font-medium">For</th>
                  <th className="py-2 pr-4 font-medium">Expression</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filteredRules.map((rule: AlertRule) => (
                  <tr key={`${rule.group}/${rule.name}`} className="transition hover:bg-surface-hover">
                    <td className="py-2.5 pl-4 pr-2">
                      <SeverityBadge severity={rule.severity} />
                    </td>
                    <td className="py-2.5 pr-2 text-content-primary">{rule.name}</td>
                    <td className="py-2.5 pr-2 text-content-secondary">{rule.group}</td>
                    <td className="py-2.5 pr-2">
                      <AlertStateBadge state={rule.state} />
                    </td>
                    <td className="py-2.5 pr-2 text-content-secondary">{rule.activeCount}</td>
                    <td className="py-2.5 pr-2 text-content-muted">{formatFor(rule.durationSeconds)}</td>
                    <td className="py-2.5 pr-4">
                      <code className="line-clamp-1 max-w-md font-mono text-[11px] text-content-muted">{rule.query}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
