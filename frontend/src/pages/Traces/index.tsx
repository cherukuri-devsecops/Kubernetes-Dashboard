import { useMemo, useState } from "react";
import clsx from "clsx";

import { SpanStatusBadge } from "@/components/common/badges";
import { formatDuration, formatRelativeTime, generateTraces, type SpanStatus, type Trace, type TraceSpan } from "@/utils/mockData";

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

type SpanCategory = "http" | "database" | "cache" | "external" | "other";

const CATEGORY_COLOR: Record<SpanCategory, string> = {
  http: "#a78bfa",
  database: "#6ea8fe",
  cache: "#31d0aa",
  external: "#f5c66a",
  other: "#8892a6",
};

const CATEGORY_LABEL: Record<SpanCategory, string> = {
  http: "HTTP Request",
  database: "Database",
  cache: "Cache",
  external: "External API",
  other: "Other",
};

function categoryOf(span: TraceSpan, isRoot: boolean): SpanCategory {
  if (isRoot) return "http";
  const service = span.service.toLowerCase();
  if (service.includes("postgres") || service.includes("db") || service.includes("sql")) return "database";
  if (service.includes("redis") || service.includes("cache")) return "cache";
  if (service.includes("auth") || service.includes("payments") || service.includes("gateway")) return "external";
  return "other";
}

export function TracesPage() {
  const traces = useMemo(() => generateTraces(), []);
  const [selectedId, setSelectedId] = useState<string>(traces[0]?.id ?? "");
  const [statusFilter, setStatusFilter] = useState<"all" | SpanStatus>("all");
  const [durationFilter, setDurationFilter] = useState<DurationFilterKey>("any");

  const minDuration = DURATION_FILTERS.find((f) => f.key === durationFilter)?.min ?? 0;
  const filtered = traces.filter(
    (trace) => (statusFilter === "all" || trace.status === statusFilter) && trace.durationMs >= minDuration,
  );

  const selected: Trace | undefined = filtered.find((trace) => trace.id === selectedId) ?? filtered[0];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div>
        <p className="text-sm text-brand-400">Traces</p>
        <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Trace Explorer</h2>
        <p className="mt-1 text-sm text-content-muted">Simulated request traces across services.</p>
      </div>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
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
              <li className="px-4 py-8 text-center text-sm text-content-muted">No traces match the current filters.</li>
            ) : (
              filtered.map((trace) => (
                <li key={trace.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(trace.id)}
                    className={clsx(
                      "flex w-full flex-col gap-1 px-4 py-3 text-left transition hover:bg-surface-hover",
                      trace.id === selected?.id ? "bg-surface-hover" : "",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-content-primary">{trace.operation}</span>
                      <SpanStatusBadge status={trace.status} />
                    </div>
                    <div className="flex items-center justify-between text-xs text-content-muted">
                      <span>{trace.rootService}</span>
                      <span>
                        {formatDuration(trace.durationMs)} · {formatRelativeTime(trace.timestamp)}
                      </span>
                    </div>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        <div className="rounded-lg border border-line bg-surface p-4">
          {selected ? (
            <div>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-medium text-content-primary">{selected.operation}</h3>
                  <p className="text-xs text-content-muted">
                    {selected.rootService} · {formatDuration(selected.durationMs)} total · Trace ID {selected.id}
                  </p>
                </div>
                <SpanStatusBadge status={selected.status} />
              </div>

              <div className="mb-2 flex justify-between text-[10px] text-content-muted">
                <span>0ms</span>
                <span>{Math.round(selected.durationMs / 2)}ms</span>
                <span>{formatDuration(selected.durationMs)}</span>
              </div>

              <div className="space-y-2.5">
                {selected.spans.map((span, index) => {
                  const leftPct = (span.startOffsetMs / selected.durationMs) * 100;
                  const widthPct = Math.max((span.durationMs / selected.durationMs) * 100, 1.5);
                  const category = categoryOf(span, index === 0);
                  return (
                    <div key={span.id}>
                      <div className="mb-1 flex items-center justify-between text-xs">
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
                            width: `${widthPct}%`,
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
            <p className="text-sm text-content-muted">Select a trace to see its span waterfall.</p>
          )}
        </div>
      </section>
    </div>
  );
}
