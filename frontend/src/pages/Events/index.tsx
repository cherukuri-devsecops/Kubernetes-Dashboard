import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, Layers, Pause, Play, RefreshCw, Search, TriangleAlert, Zap } from "lucide-react";
import clsx from "clsx";

import { StatTile } from "@/components/cards/StatTile";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { EventTypeBadge } from "@/components/common/badges";
import { FilterChips } from "@/components/common/FilterChips";
import {
  ChartCard,
  chartAxisColor,
  chartGridColor,
  chartTooltipContentStyle,
  chartTooltipLabelStyle,
  eventColors,
} from "@/components/charts/ChartCard";
import { fetchEvents, type ClusterEvent, type EventType } from "@/services/events";
import { formatRelativeTime } from "@/utils/mockData";

const EVENT_TYPES: { key: EventType; label: string }[] = [
  { key: "Normal", label: "Normal" },
  { key: "Warning", label: "Warning" },
];

const selectClass =
  "h-8 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20";

const REFRESH_INTERVAL_MS = 15000;
const CHART_WINDOW_MINUTES = 60;
const CHART_BUCKETS = 12;

/** Buckets events into equal windows over the last hour, split by type. */
function bucketEventsByType(events: ClusterEvent[]): { time: string; normal: number; warning: number }[] {
  const now = Date.now();
  const windowMs = CHART_WINDOW_MINUTES * 60 * 1000;
  const bucketMs = windowMs / CHART_BUCKETS;
  const buckets = Array.from({ length: CHART_BUCKETS }, (_, index) => ({
    time: new Date(now - (CHART_BUCKETS - 1 - index) * bucketMs).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }),
    normal: 0,
    warning: 0,
  }));

  for (const event of events) {
    const age = now - event.lastSeen.getTime();
    if (age < 0 || age > windowMs) continue;
    const index = CHART_BUCKETS - 1 - Math.floor(age / bucketMs);
    if (index < 0 || index >= CHART_BUCKETS) continue;
    if (event.type === "Warning") buckets[index].warning += 1;
    else buckets[index].normal += 1;
  }

  return buckets;
}

export function EventsPage() {
  const [paused, setPaused] = useState(false);
  const [events, setEvents] = useState<ClusterEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [types, setTypes] = useState<Set<EventType>>(() => new Set<EventType>(["Normal", "Warning"]));
  const [namespace, setNamespace] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;

    async function load() {
      try {
        const list = await fetchEvents(null);
        if (cancelled) return;
        setEvents(list);
        setError(null);
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load events");
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
  }, [paused]);

  const namespaces = useMemo(
    () => Array.from(new Set(events.map((event) => event.namespace))).sort(),
    [events],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      if (!types.has(event.type)) return false;
      if (namespace !== "all" && event.namespace !== namespace) return false;
      if (!needle) return true;
      return (
        event.reason.toLowerCase().includes(needle) ||
        event.object.toLowerCase().includes(needle) ||
        event.message.toLowerCase().includes(needle)
      );
    });
  }, [events, types, namespace, query]);

  // No first-row fallback here: the stream reorders every few seconds, and an
  // implicit selection would keep jumping to whatever arrived last.
  const selected = filtered.find((event) => event.id === selectedId) ?? null;

  const buckets = useMemo(() => bucketEventsByType(events), [events]);

  const counts = useMemo(
    () => ({
      total: events.length,
      warnings: events.filter((event) => event.type === "Warning").length,
      normal: events.filter((event) => event.type === "Normal").length,
      namespaces: namespaces.length,
    }),
    [events, namespaces],
  );

  function toggleType(type: EventType) {
    setTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  const columns: Column<ClusterEvent>[] = [
    { key: "lastSeen", header: "Last Seen", render: (event) => formatRelativeTime(event.lastSeen) },
    { key: "type", header: "Type", render: (event) => <EventTypeBadge type={event.type} /> },
    { key: "reason", header: "Reason", cellClassName: "text-content-primary", render: (event) => event.reason },
    { key: "object", header: "Object", render: (event) => event.object },
    { key: "namespace", header: "Namespace", render: (event) => event.namespace },
    { key: "count", header: "Count", render: (event) => event.count },
    {
      key: "message",
      header: "Message",
      render: (event) => <span className="line-clamp-1 max-w-md">{event.message}</span>,
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Events</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Cluster event stream</h2>
          <p className="mt-0.5 text-xs text-content-muted">Live events read directly from the cluster API.</p>
        </div>
        <div className="flex items-center gap-2">
          <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && !paused && "animate-spin")} aria-hidden="true" />
          <button
            type="button"
            onClick={() => setPaused((current) => !current)}
            className="flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            {paused ? <Play className="h-3.5 w-3.5" aria-hidden="true" /> : <Pause className="h-3.5 w-3.5" aria-hidden="true" />}
            {paused ? "Resume stream" : "Pause stream"}
          </button>
        </div>
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Recent Events" value={counts.total} icon={Zap} tone="neutral" hint={paused ? "paused" : "live"} />
        <StatTile label="Warning Events" value={counts.warnings} icon={TriangleAlert} tone={counts.warnings > 0 ? "amber" : "green"} />
        <StatTile label="Normal Events" value={counts.normal} icon={Activity} tone="blue" />
        <StatTile label="Namespaces Affected" value={counts.namespaces} icon={Layers} tone="neutral" />
      </section>

      <ChartCard title="Events Over Time" subtitle="Last 60 minutes, by type" height={180}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={buckets} margin={{ left: -24, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid stroke={chartGridColor} vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={{ stroke: chartGridColor }} tickLine={false} minTickGap={20} />
            <YAxis tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={false} tickLine={false} width={44} allowDecimals={false} />
            <Tooltip contentStyle={chartTooltipContentStyle} labelStyle={chartTooltipLabelStyle} cursor={{ fill: "var(--color-surface-hover)" }} />
            <Legend wrapperStyle={{ fontSize: 11, color: chartAxisColor }} iconType="circle" iconSize={8} />
            <Bar
              dataKey="normal"
              name="Normal"
              stackId="events"
              fill={eventColors.normal}
              stroke="var(--color-surface)"
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Bar
              dataKey="warning"
              name="Warning"
              stackId="events"
              fill={eventColors.warning}
              stroke="var(--color-surface)"
              strokeWidth={2}
              radius={[3, 3, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
        <FilterChips label="Type" options={EVENT_TYPES} selected={types} onToggle={toggleType} />

        <label className="flex items-center gap-2">
          <span className="text-xs text-content-muted">Namespace</span>
          <select value={namespace} onChange={(event) => setNamespace(event.target.value)} className={selectClass}>
            <option value="all">All namespaces</option>
            {namespaces.map((ns) => (
              <option key={ns} value={ns}>
                {ns}
              </option>
            ))}
          </select>
        </label>

        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-muted" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by reason, object, or message…"
            className="h-8 w-full rounded-md border border-line bg-surface-hover/60 pl-8 pr-2.5 text-xs text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
          />
        </div>

        <span className="text-xs text-content-muted">
          {filtered.length} of {events.length} events
        </span>
      </div>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <DataTable
          columns={columns}
          rows={filtered}
          rowKey={(event) => event.id}
          onRowClick={(event) => setSelectedId(event.id)}
          selectedKey={selected?.id ?? null}
          emptyMessage={loading ? "Loading events…" : "No events match the current filters."}
          minWidth={900}
        />

        <div className="rounded-lg border border-line bg-surface p-4">
          <h3 className="mb-3 text-sm font-medium text-content-primary">Event Detail</h3>
          {selected ? (
            <div className="space-y-3 text-xs">
              <div className="flex items-center gap-2">
                <EventTypeBadge type={selected.type} />
                <span className="text-sm font-medium text-content-primary">{selected.reason}</span>
              </div>
              <DetailRow label="Object" value={selected.object} />
              <DetailRow label="Namespace" value={selected.namespace} />
              <DetailRow label="Source" value={selected.source} />
              <DetailRow label="Count" value={`${selected.count}×`} />
              <DetailRow label="First seen" value={formatRelativeTime(selected.firstSeen)} />
              <DetailRow label="Last seen" value={formatRelativeTime(selected.lastSeen)} />
              <div>
                <p className="mb-1 text-content-muted">Message</p>
                <p className="rounded-md bg-surface-hover/60 p-2 text-content-secondary">{selected.message}</p>
              </div>
              <div className="flex gap-2 pt-1">
                <Link
                  to="/logs"
                  className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                >
                  View in Logs
                </Link>
              </div>
            </div>
          ) : (
            <p className="text-xs text-content-muted">Select an event to see its details.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-content-muted">{label}</p>
      <p className="break-words text-content-primary">{value}</p>
    </div>
  );
}
