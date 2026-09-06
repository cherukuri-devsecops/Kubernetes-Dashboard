import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, CircleCheck, Clock, LifeBuoy, Search, ShieldAlert, Sparkles, TriangleAlert } from "lucide-react";

import { StatTile } from "@/components/cards/StatTile";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { FilterChips } from "@/components/common/FilterChips";
import { SegmentedTabs } from "@/components/common/SegmentedTabs";
import { IncidentSeverityBadge, IncidentStatusBadge } from "@/components/common/badges";
import {
  fetchIncidents,
  meanTimeToResolveMinutes,
  updateIncidentStatus,
  type Incident,
  type IncidentSeverity,
  type IncidentStatus,
} from "@/services/incidents";
import { formatRelativeTime } from "@/utils/format";

const SEVERITIES: { key: IncidentSeverity; label: string }[] = [
  { key: "sev1", label: "SEV1" },
  { key: "sev2", label: "SEV2" },
  { key: "sev3", label: "SEV3" },
];

type ViewTab = "active" | "resolved" | "all";

const TABS: { key: ViewTab; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "resolved", label: "Resolved" },
  { key: "all", label: "All" },
];

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 24) return rest > 0 ? `${hours}h ${rest}m` : `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function incidentDuration(incident: Incident): string {
  const end = incident.resolvedAt ?? new Date();
  return formatMinutes(Math.max(1, Math.round((end.getTime() - incident.openedAt.getTime()) / 60000)));
}

const REFRESH_INTERVAL_MS = 30000;

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<ViewTab>("active");
  const [severities, setSeverities] = useState<Set<IncidentSeverity>>(() => new Set<IncidentSeverity>(["sev1", "sev2", "sev3"]));
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await fetchIncidents();
      setIncidents(list);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load incidents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return incidents.filter((incident) => {
      if (tab === "active" && incident.status === "resolved") return false;
      if (tab === "resolved" && incident.status !== "resolved") return false;
      if (!severities.has(incident.severity)) return false;
      if (!needle) return true;
      return (
        incident.title.toLowerCase().includes(needle) ||
        incident.id.toLowerCase().includes(needle) ||
        incident.service.toLowerCase().includes(needle)
      );
    });
  }, [incidents, tab, severities, query]);

  const selected = filtered.find((incident) => incident.id === selectedId) ?? filtered[0] ?? null;

  const counts = useMemo(
    () => ({
      open: incidents.filter((incident) => incident.status === "open").length,
      investigating: incidents.filter((incident) => incident.status === "investigating").length,
      mitigated: incidents.filter((incident) => incident.status === "mitigated").length,
      resolved: incidents.filter((incident) => incident.status === "resolved").length,
      mttr: meanTimeToResolveMinutes(incidents),
    }),
    [incidents],
  );

  function toggleSeverity(severity: IncidentSeverity) {
    setSeverities((current) => {
      const next = new Set(current);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  }

  async function advance(id: string, status: IncidentStatus, note: string) {
    try {
      const updated = await updateIncidentStatus(id, status, note);
      setIncidents((current) => current.map((incident) => (incident.id === id ? updated : incident)));
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not update the incident");
    }
  }

  const columns: Column<Incident>[] = [
    { key: "severity", header: "Severity", render: (incident) => <IncidentSeverityBadge severity={incident.severity} /> },
    { key: "id", header: "ID", cellClassName: "font-mono text-xs", render: (incident) => incident.id },
    {
      key: "title",
      header: "Title",
      cellClassName: "text-content-primary",
      render: (incident) => <span className="line-clamp-1 max-w-sm">{incident.title}</span>,
    },
    { key: "status", header: "Status", render: (incident) => <IncidentStatusBadge status={incident.status} /> },
    { key: "service", header: "Service", render: (incident) => incident.service },
    { key: "assignee", header: "Assignee", render: (incident) => incident.assignee },
    { key: "opened", header: "Opened", render: (incident) => formatRelativeTime(incident.openedAt) },
    { key: "duration", header: "Duration", render: (incident) => incidentDuration(incident) },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div>
        <p className="text-sm text-brand-400">Incidents</p>
        <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Incident management</h2>
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Open" value={counts.open} icon={ShieldAlert} tone={counts.open > 0 ? "red" : "green"} />
        <StatTile label="Investigating" value={counts.investigating} icon={Search} tone="amber" />
        <StatTile label="Mitigated" value={counts.mitigated} icon={TriangleAlert} tone="blue" />
        <StatTile label="Resolved" value={counts.resolved} icon={CircleCheck} tone="green" />
        <StatTile label="Mean Time to Resolve" value={counts.mttr === null ? "—" : formatMinutes(counts.mttr)} icon={Clock} tone="neutral" />
      </section>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
        <SegmentedTabs options={TABS} value={tab} onChange={setTab} />
        <FilterChips label="Severity" options={SEVERITIES} selected={severities} onToggle={toggleSeverity} />

        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-muted" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search incidents by title, ID, or service…"
            className="h-8 w-full rounded-md border border-line bg-surface-hover/60 pl-8 pr-2.5 text-xs text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
          />
        </div>
      </div>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <DataTable
          columns={columns}
          rows={filtered}
          rowKey={(incident) => incident.id}
          onRowClick={(incident) => setSelectedId(incident.id)}
          selectedKey={selected?.id ?? null}
          emptyMessage={loading ? "Loading incidents…" : "No incidents match the current filters."}
          minWidth={980}
        />

        {selected ? (
          <IncidentDetail incident={selected} onAdvance={advance} />
        ) : (
          <div className="rounded-lg border border-line bg-surface p-4">
            <h3 className="mb-3 text-sm font-medium text-content-primary">Incident Detail</h3>
            <p className="text-xs text-content-muted">Select an incident to see its timeline.</p>
          </div>
        )}
      </section>
    </div>
  );
}

type IncidentDetailProps = {
  incident: Incident;
  onAdvance: (id: string, status: IncidentStatus, note: string) => void;
};

function IncidentDetail({ incident, onAdvance }: IncidentDetailProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-line bg-surface p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <IncidentSeverityBadge severity={incident.severity} />
          <IncidentStatusBadge status={incident.status} />
          <span className="font-mono text-xs text-content-muted">{incident.id}</span>
        </div>
        <h3 className="text-sm font-medium text-content-primary">{incident.title}</h3>

        <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
          <Detail label="Service" value={incident.service} />
          <Detail label="Namespace" value={incident.namespace} />
          <Detail label="Assignee" value={incident.assignee} />
          <Detail label="Opened" value={formatRelativeTime(incident.openedAt)} />
          <Detail label="Duration" value={incidentDuration(incident)} />
          <Detail label="Resolved" value={incident.resolvedAt ? formatRelativeTime(incident.resolvedAt) : "—"} />
        </dl>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {incident.status === "open" ? (
            <ActionButton label="Acknowledge" onClick={() => onAdvance(incident.id, "investigating", "Acknowledged the incident")} />
          ) : null}
          {incident.status === "investigating" ? (
            <ActionButton label="Mark Mitigated" onClick={() => onAdvance(incident.id, "mitigated", "Impact mitigated, monitoring")} />
          ) : null}
          {incident.status !== "resolved" ? (
            <ActionButton label="Resolve" onClick={() => onAdvance(incident.id, "resolved", "Incident resolved")} />
          ) : null}
          <Link
            to="/alerts"
            className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            <Bell className="h-3.5 w-3.5" aria-hidden="true" />
            Related Alerts
          </Link>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-surface p-4">
        <div className="mb-2 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-400" aria-hidden="true" />
          <h3 className="text-sm font-medium text-content-primary">AI Summary</h3>
        </div>
        <p className="rounded-md bg-surface-hover/60 p-2.5 text-xs leading-5 text-content-secondary">{incident.summary}</p>
        <p className="mt-3 text-xs text-content-muted">Root cause</p>
        <p className="mt-1 text-xs leading-5 text-content-primary">
          {incident.rootCause ?? "Analysis has not run for this incident yet."}
        </p>
        {incident.linkedAlerts.length > 0 ? (
          <>
            <p className="mt-3 text-xs text-content-muted">Linked alerts</p>
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {incident.linkedAlerts.map((alert) => (
                <li key={alert} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-content-secondary">
                  {alert}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>

      <div className="rounded-lg border border-line bg-surface p-4">
        <div className="mb-3 flex items-center gap-2">
          <LifeBuoy className="h-4 w-4 text-content-muted" aria-hidden="true" />
          <h3 className="text-sm font-medium text-content-primary">Timeline</h3>
        </div>
        <ol className="space-y-3">
          {incident.timeline.map((update, index) => (
            <li key={update.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand" />
                {index < incident.timeline.length - 1 ? <span className="mt-1 w-px flex-1 bg-line" /> : null}
              </div>
              <div className="pb-1 text-xs">
                <p className="text-content-primary">{update.text}</p>
                <p className="mt-0.5 text-[11px] text-content-muted">
                  {update.actor} · {formatRelativeTime(update.at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-content-muted">{label}</dt>
      <dd className="text-content-primary">{value}</dd>
    </div>
  );
}

function ActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
    >
      {label}
    </button>
  );
}
