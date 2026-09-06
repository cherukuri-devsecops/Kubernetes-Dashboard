import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Search, X } from "lucide-react";
import clsx from "clsx";

import { LevelBadge } from "@/components/common/badges";
import { type LogLevel } from "@/services/logs";
import { searchLogs, type LogEntry } from "@/services/logs";

const LEVELS: LogLevel[] = ["debug", "info", "warn", "error"];
const REFRESH_INTERVAL_MS = 5000;
const RANGE_MINUTES = 30;
const LIMIT = 300;

function levelOf(line: string): LogLevel {
  const lower = line.toLowerCase();
  if (/\b(error|err|fatal|panic)\b/.test(lower)) return "error";
  if (/\b(warn|warning)\b/.test(lower)) return "warn";
  if (/\bdebug\b/.test(lower)) return "debug";
  return "info";
}

type Facet = { value: string; count: number };

function buildFacet(entries: LogEntry[], pick: (entry: LogEntry) => string | undefined): Facet[] {
  const counts = new Map<string, number>();
  for (const entry of entries) {
    const value = pick(entry);
    if (!value) continue;
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
}

function FacetGroup({
  title,
  facets,
  activeValue,
  onSelect,
}: {
  title: string;
  facets: Facet[];
  activeValue: string | null;
  onSelect: (value: string | null) => void;
}) {
  if (facets.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-content-muted">
        {title} <span className="text-content-muted">{facets.length}</span>
      </p>
      <ul className="space-y-0.5">
        {facets.map((facet) => (
          <li key={facet.value}>
            <button
              type="button"
              onClick={() => onSelect(activeValue === facet.value ? null : facet.value)}
              className={clsx(
                "flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left text-xs transition",
                activeValue === facet.value
                  ? "bg-brand/[0.16] text-content-primary"
                  : "text-content-secondary hover:bg-surface-hover hover:text-content-primary",
              )}
            >
              <span className="truncate">{facet.value}</span>
              <span className="shrink-0 text-content-muted">{facet.count}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [frozenEntries, setFrozenEntries] = useState<LogEntry[]>([]);
  const [activeLevels, setActiveLevels] = useState<Set<LogLevel>>(new Set(LEVELS));
  const [namespaceFilter, setNamespaceFilter] = useState<string | null>(null);
  const [podFilter, setPodFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const queryRef = useRef(query);
  queryRef.current = query;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const { entries: fetched } = await searchLogs({
          query: queryRef.current || undefined,
          rangeMinutes: RANGE_MINUTES,
          limit: LIMIT,
        });
        if (cancelled) return;
        setEntries(fetched);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load logs");
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [query]);

  const logs = paused ? frozenEntries : entries;

  const namespaceFacets = useMemo(() => buildFacet(logs, (e) => e.namespace), [logs]);
  const podFacets = useMemo(() => buildFacet(logs, (e) => e.pod), [logs]);
  const containerFacets = useMemo(() => buildFacet(logs, (e) => e.container), [logs]);
  const levelFacets = useMemo(() => buildFacet(logs, (e) => levelOf(e.line)), [logs]);

  const filtered = useMemo(() => {
    return logs.filter((log) => {
      if (!activeLevels.has(levelOf(log.line))) return false;
      if (namespaceFilter && log.namespace !== namespaceFilter) return false;
      if (podFilter && log.pod !== podFilter) return false;
      return true;
    });
  }, [logs, activeLevels, namespaceFilter, podFilter]);

  function toggleLevel(level: LogLevel) {
    setActiveLevels((current) => {
      const next = new Set(current);
      if (next.has(level)) {
        next.delete(level);
      } else {
        next.add(level);
      }
      return next;
    });
  }

  function togglePause() {
    if (!paused) setFrozenEntries(entries);
    setPaused((current) => !current);
  }

  function clearFilters() {
    setNamespaceFilter(null);
    setPodFilter(null);
    setActiveLevels(new Set(LEVELS));
    setQuery("");
  }

  const hasActiveFilters = namespaceFilter !== null || podFilter !== null || activeLevels.size < LEVELS.length || query.length > 0;

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-brand-400">Logs</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Log Explorer</h2>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-muted">
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search logs…"
              className="w-40 bg-transparent text-content-primary outline-none placeholder:text-content-muted sm:w-56"
            />
          </div>
          <button
            type="button"
            onClick={togglePause}
            className="flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-secondary transition hover:text-content-primary"
          >
            {paused ? <Play className="h-3.5 w-3.5" aria-hidden="true" /> : <Pause className="h-3.5 w-3.5" aria-hidden="true" />}
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)_280px]">
        <aside className="hidden flex-col gap-4 rounded-lg border border-line bg-surface p-3 xl:flex">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium text-content-primary">Log Labels</h3>
            {hasActiveFilters ? (
              <button type="button" onClick={clearFilters} className="text-[11px] text-content-muted transition hover:text-content-primary">
                Clear all
              </button>
            ) : null}
          </div>
          <FacetGroup title="Namespace" facets={namespaceFacets} activeValue={namespaceFilter} onSelect={setNamespaceFilter} />
          <FacetGroup title="Pod" facets={podFacets} activeValue={podFilter} onSelect={setPodFilter} />
          <FacetGroup title="Container" facets={containerFacets} activeValue={null} onSelect={() => undefined} />
          <FacetGroup title="Level" facets={levelFacets} activeValue={null} onSelect={() => undefined} />
        </aside>

        <section className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3">
            {LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => toggleLevel(level)}
                className={clsx(
                  "rounded-full border px-2.5 py-1 text-xs font-medium capitalize transition",
                  activeLevels.has(level)
                    ? "border-brand/40 bg-brand/10 text-brand-400"
                    : "border-line text-content-muted hover:text-content-primary",
                )}
              >
                {level}
              </button>
            ))}
            {namespaceFilter ? (
              <span className="flex items-center gap-1 rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs text-brand-400">
                ns: {namespaceFilter}
                <button type="button" onClick={() => setNamespaceFilter(null)}>
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            ) : null}
            {podFilter ? (
              <span className="flex items-center gap-1 rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs text-brand-400">
                pod: {podFilter}
                <button type="button" onClick={() => setPodFilter(null)}>
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            ) : null}
          </div>

          <div className="rounded-lg border border-line bg-surface">
            <div className="max-h-[38rem] overflow-y-auto font-mono text-xs">
              {error ? (
                <p className="px-4 py-8 text-center text-content-muted">{error}</p>
              ) : filtered.length === 0 ? (
                <p className="px-4 py-8 text-center text-content-muted">No log lines match the current filters.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {filtered
                    .slice()
                    .reverse()
                    .map((log, index) => (
                      <li key={`${log.timestamp}-${index}`}>
                        <button
                          type="button"
                          onClick={() => setSelected(log)}
                          className={clsx(
                            "flex w-full flex-wrap items-start gap-2 px-4 py-2 text-left transition hover:bg-surface-hover",
                            selected === log ? "bg-surface-hover" : "",
                          )}
                        >
                          <span className="shrink-0 text-content-muted">
                            {new Date(Number(log.timestamp) / 1_000_000).toLocaleTimeString()}
                          </span>
                          <LevelBadge level={levelOf(log.line)} />
                          <span className="shrink-0 text-content-secondary">
                            {log.namespace}/{log.pod}
                            {log.container ? `/${log.container}` : ""}
                          </span>
                          <span className="truncate text-content-primary">{log.line}</span>
                        </button>
                      </li>
                    ))}
                </ul>
              )}
            </div>
          </div>
        </section>

        <aside className="hidden rounded-lg border border-line bg-surface p-3 xl:block">
          <h3 className="mb-3 text-xs font-medium text-content-primary">Log Details</h3>
          {selected ? (
            <dl className="space-y-2.5 text-xs">
              <div>
                <dt className="text-content-muted">Timestamp</dt>
                <dd className="text-content-primary">{new Date(Number(selected.timestamp) / 1_000_000).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Level</dt>
                <dd>
                  <LevelBadge level={levelOf(selected.line)} />
                </dd>
              </div>
              <div>
                <dt className="text-content-muted">Namespace</dt>
                <dd className="text-content-primary">{selected.namespace}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Pod</dt>
                <dd className="text-content-primary">{selected.pod}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Container</dt>
                <dd className="text-content-primary">{selected.container || "—"}</dd>
              </div>
              <div>
                <dt className="mb-1 text-content-muted">Message</dt>
                <dd className="whitespace-pre-wrap break-words rounded-md bg-surface-hover/60 p-2 font-mono text-[11px] text-content-primary">
                  {selected.line}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-xs text-content-muted">Select a log line to see its full details.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
