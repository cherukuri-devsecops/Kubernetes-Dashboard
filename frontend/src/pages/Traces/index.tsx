import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import clsx from "clsx";

import { SpanStatusBadge } from "@/components/common/badges";
import {
  fetchTrace,
  fetchTraceServices,
  fetchTraces,
  traceStartedAt,
  type SpanStatus,
  type Trace,
  type TraceSpan,
  type TraceSummary,
} from "@/services/traces";
import { formatDuration, formatRelativeTime } from "@/utils/format";

const DURATION_FILTERS = [
  { key: "any", label: "Any duration", min: 0 },
  { key: "100", label: "> 100ms", min: 100 },
  { key: "500", label: "> 500ms", min: 500 },
  { key: "1000", label: "> 1s", min: 1000 },
] as const;
type DurationFilterKey = (typeof DURATION_FILTERS)[number]["key"];

const STATUS_FILTERS: { key: "all" | SpanStatus; label: string }[] = [
  { key: "all", label: "All" },
  { key: "ok", label: "OK" },
  { key: "error", label: "Error" },
];

const RANGE_MINUTES = 60;
const REFRESH_INTERVAL_MS = 20000;

type SpanCategory = "http" | "database" | "cache" | "messaging" | "internal";

const CATEGORY_COLOR: Record<SpanCategory, string> = {
  http: "#a78bfa",
  database: "#6ea8fe",
  cache: "#31d0aa",
  messaging: "#f5c66a",
  internal: "#8892a6",
};

const CATEGORY_LABEL: Record<SpanCategory, string> = {
  http: "HTTP",
  database: "Database",
  cache: "Cache",
  messaging: "Messaging",
  internal: "Internal",
};

/** Categorised from the span's own OTel attributes and kind, not its name. */
function categoryOf(span: TraceSpan): SpanCategory {
  const attributes = span.attributes ?? {};
  if ("db.system" in attributes) return "database";
  if ("messaging.system" in attributes) return "messaging";
  const target = String(attributes["db.system"] ?? attributes["net.peer.name"] ?? "").toLowerCase();
  if (target.includes("redis") || target.includes("memcache")) return "cache";
  if ("http.method" in attributes || "http.route" in attributes || "url.path" in attributes) return "http";
  if (span.kind === "SPAN_KIND_SERVER" || span.kind === "SPAN_KIND_CLIENT") return "http";
  return "internal";
}

export function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [services, setServices] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Trace | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | SpanStatus>("all");
  const [durationFilter, setDurationFilter] = useState<DurationFilterKey>("any");
  const [service, setService] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const minDuration = DURATION_FILTERS.find((filter) => filter.key === durationFilter)?.min ?? 0;

  useEffect(() => {
    fetchTraceServices()
      .then(setServices)
      .catch(() => setServices([]));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const list = await fetchTraces({
          limit: 30,
          rangeMinutes: RANGE_MINUTES,
          service: service === "all" ? undefined : service,
          minDurationMs: minDuration,
        });
        if (cancelled) return;
        setTraces(list);
        setError(null);
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load traces");
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
  }, [service, minDuration]);

  const filtered = useMemo(
    () => traces.filter((trace) => statusFilter === "all" || trace.status === statusFilter),
    [traces, statusFilter],
  );

  const activeId = filtered.find((trace) => trace.id === selectedId)?.id ?? filtered[0]?.id ?? null;

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetchTrace(activeId)
      .then((trace) => {
        if (!cancelled) setDetail(trace);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Traces</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Trace Explorer</h2>
          <p className="mt-1 text-sm text-content-muted">
            Distributed traces read from Tempo, last {RANGE_MINUTES} minutes.
          </p>
        </div>
        <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && "animate-spin")} aria-hidden="true" />
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-content-muted">Service</span>
          <select
            value={service}
            onChange={(event) => setService(event.target.value)}
            className="h-8 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-secondary outline-none"
          >
            <option value="all">All services</option>
            {services.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-content-muted">Duration</span>
          <select
            value={durationFilter}
            onChange={(event) => setDurationFilter(event.target.value as DurationFilterKey)}
            className="h-8 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-secondary outline-none"
          >
            {DURATION_FILTERS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="mr-1 text-xs text-content-muted">Status</span>
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setStatusFilter(option.key)}
              className={clsx(
                "h-8 rounded-md px-2.5 text-xs transition",
                statusFilter === option.key
                  ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                  : "text-content-muted hover:text-content-primary",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-content-muted">
          Showing {filtered.length} of {traces.length}
        </span>
      </div>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="rounded-lg border border-line bg-surface">
          <ul className="max-h-[36rem] divide-y divide-line overflow-y-auto">
            {filtered.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-content-muted">
                {loading ? "Loading traces…" : "No traces match the current filters."}
              </li>
            ) : (
              filtered.map((trace) => (
                <li key={trace.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(trace.id)}
                    className={clsx(
                      "flex w-full flex-col gap-1 px-4 py-3 text-left transition hover:bg-surface-hover",
                      trace.id === activeId ? "bg-surface-hover" : "",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-content-primary">{trace.operation}</span>
                      <SpanStatusBadge status={trace.status} />
                    </div>
                    <div className="flex items-center justify-between text-xs text-content-muted">
                      <span className="truncate">
                        {trace.rootService} · {trace.spanCount} span{trace.spanCount === 1 ? "" : "s"}
                      </span>
                      <span className="shrink-0">
                        {formatDuration(trace.durationMs)} · {formatRelativeTime(traceStartedAt(trace))}
                      </span>
                    </div>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        <div className="rounded-lg border border-line bg-surface p-4">
          {detail ? (
            <div>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-medium text-content-primary">{detail.operation}</h3>
                  <p className="truncate text-xs text-content-muted">
                    {detail.rootService} · {formatDuration(detail.durationMs)} total · Trace ID {detail.id}
                  </p>
                </div>
                <SpanStatusBadge status={detail.status} />
              </div>

              <div className="mb-2 flex justify-between text-[10px] text-content-muted">
                <span>0ms</span>
                <span>{Math.round(detail.durationMs / 2)}ms</span>
                <span>{formatDuration(detail.durationMs)}</span>
              </div>

              <div className="max-h-[28rem] space-y-2.5 overflow-y-auto">
                {detail.spans.map((span) => {
                  const total = detail.durationMs || 1;
                  const leftPct = Math.min((span.startOffsetMs / total) * 100, 100);
                  const widthPct = Math.max((span.durationMs / total) * 100, 1.5);
                  const category = categoryOf(span);
                  return (
                    <div key={span.id}>
                      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                        <span className="truncate text-content-secondary">
                          {span.name} <span className="text-content-muted">· {span.service}</span>
                        </span>
                        <span className="shrink-0 text-content-muted">{formatDuration(span.durationMs)}</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-surface-hover">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            marginLeft: `${leftPct}%`,
                            width: `${Math.min(widthPct, 100 - leftPct)}%`,
                            backgroundColor: span.status === "error" ? "#ff6b6b" : CATEGORY_COLOR[category],
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4 flex flex-wrap gap-3 border-t border-line pt-3">
                {(Object.keys(CATEGORY_LABEL) as SpanCategory[]).map((category) => (
                  <span key={category} className="flex items-center gap-1.5 text-[11px] text-content-muted">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: CATEGORY_COLOR[category] }} />
                    {CATEGORY_LABEL[category]}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-content-muted">
              {activeId ? "Loading trace…" : "Select a trace to see its span waterfall."}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
