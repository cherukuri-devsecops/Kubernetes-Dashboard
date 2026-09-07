import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Radio, Search, Trash2, X } from "lucide-react";
import clsx from "clsx";

import { LevelBadge } from "@/components/common/badges";
import { SegmentedTabs } from "@/components/common/SegmentedTabs";
import { searchLogs, streamPodLogs, type LogEntry, type LogLevel } from "@/services/logs";
import { fetchNamespaces, fetchPods, type K8sPod } from "@/services/kubernetes";

const LEVELS: LogLevel[] = ["debug", "info", "warn", "error"];
const REFRESH_INTERVAL_MS = 5000;
const RANGE_MINUTES = 30;
const LIMIT = 300;

type ViewMode = "search" | "tail";

/** Lines held in the live tail before the oldest are dropped. */
const TAIL_CAP = 2000;
const TAIL_LINES = 200;

const selectClass =
  "h-8 min-w-0 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20";

type TailLine = { id: number; text: string };

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
  const [mode, setMode] = useState<ViewMode>("search");
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
    if (mode !== "search") return;
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
  }, [query, mode]);

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
          <p className="mt-0.5 text-xs text-content-muted">
            {mode === "search"
              ? `Indexed history from Loki, last ${RANGE_MINUTES} minutes.`
              : "Live tail straight from the Kubernetes API, like kubectl logs -f."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedTabs
            value={mode}
            onChange={setMode}
            size="sm"
            options={[
              { key: "search", label: "Search" },
              { key: "tail", label: "Live tail" },
            ]}
          />
          {mode === "search" ? (
            <>
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
            </>
          ) : null}
        </div>
      </div>

      {mode === "tail" ? <LiveTail /> : (
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
      )}
    </div>
  );
}

/** Tails one pod's logs live from the Kubernetes API, the way `kubectl logs -f`
 * does — separate from the Loki search above, which is historical and indexed. */
function LiveTail() {
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [namespace, setNamespace] = useState("");
  const [pods, setPods] = useState<K8sPod[]>([]);
  const [pod, setPod] = useState("");
  const [container, setContainer] = useState("");
  const [lines, setLines] = useState<TailLine[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lineId = useRef(0);

  useEffect(() => {
    fetchNamespaces()
      .then((list) => setNamespaces(list.map((item) => item.name)))
      .catch(() => setNamespaces([]));
  }, []);

  useEffect(() => {
    if (!namespace) {
      setPods([]);
      return;
    }
    let cancelled = false;
    fetchPods(namespace)
      .then((list) => {
        if (cancelled) return;
        setPods(list);
        setPod((current) => (list.some((item) => item.name === current) ? current : ""));
      })
      .catch(() => {
        if (!cancelled) setPods([]);
      });
    return () => {
      cancelled = true;
    };
  }, [namespace]);

  const containerNames = useMemo(
    () => pods.find((item) => item.name === pod)?.containerNames ?? [],
    [pods, pod],
  );

  // Stop the stream when the component goes away, so the backend can release
  // its reader thread and the connection to the API server.
  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (!follow) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines, follow]);

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }

  function start() {
    if (!namespace || !pod) return;
    abortRef.current?.abort();

    const controller = new AbortController();
    abortRef.current = controller;
    setLines([]);
    setError(null);
    setStreaming(true);

    void streamPodLogs({
      namespace,
      pod,
      container: container || undefined,
      tailLines: TAIL_LINES,
      signal: controller.signal,
      onLine: (text) =>
        setLines((current) => {
          const next = [...current, { id: lineId.current++, text }];
          return next.length > TAIL_CAP ? next.slice(next.length - TAIL_CAP) : next;
        }),
      onError: (message) => {
        setError(message);
        setStreaming(false);
      },
      onClose: () => setStreaming(false),
    });
  }

  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3">
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-content-muted">Namespace</span>
          <select
            value={namespace}
            onChange={(event) => {
              stop();
              setNamespace(event.target.value);
              setPod("");
              setContainer("");
            }}
            className={selectClass}
          >
            <option value="">Select…</option>
            {namespaces.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5">
          <span className="text-xs text-content-muted">Pod</span>
          <select
            value={pod}
            onChange={(event) => {
              stop();
              setPod(event.target.value);
              setContainer("");
            }}
            disabled={!namespace}
            className={clsx(selectClass, "max-w-[18rem]", !namespace && "opacity-50")}
          >
            <option value="">Select…</option>
            {pods.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        {containerNames.length > 1 ? (
          <label className="flex items-center gap-1.5">
            <span className="text-xs text-content-muted">Container</span>
            <select
              value={container}
              onChange={(event) => {
                stop();
                setContainer(event.target.value);
              }}
              className={selectClass}
            >
              <option value="">Default</option>
              {containerNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <button
          type="button"
          onClick={streaming ? stop : start}
          disabled={!namespace || !pod}
          className={clsx(
            "flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
            streaming
              ? "border border-line text-content-secondary hover:bg-surface-hover hover:text-content-primary"
              : "bg-brand text-white hover:bg-brand-600",
          )}
        >
          {streaming ? <Pause className="h-3.5 w-3.5" aria-hidden="true" /> : <Radio className="h-3.5 w-3.5" aria-hidden="true" />}
          {streaming ? "Stop" : "Start tail"}
        </button>

        <label className="flex items-center gap-1.5 text-xs text-content-muted">
          <input type="checkbox" checked={follow} onChange={() => setFollow((value) => !value)} className="accent-brand" />
          Auto-scroll
        </label>

        {lines.length > 0 ? (
          <button
            type="button"
            onClick={() => setLines([])}
            className="flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Clear
          </button>
        ) : null}

        <span className="ml-auto flex items-center gap-1.5 text-xs text-content-muted">
          {streaming ? (
            <>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal-green" />
              streaming · {lines.length} line{lines.length === 1 ? "" : "s"}
            </>
          ) : (
            `${lines.length} line${lines.length === 1 ? "" : "s"}`
          )}
        </span>
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <div className="rounded-lg border border-line bg-surface">
        <div ref={scrollRef} className="max-h-[38rem] overflow-y-auto p-3 font-mono text-xs">
          {lines.length === 0 ? (
            <p className="py-8 text-center text-content-muted">
              {streaming
                ? "Waiting for the pod to write a log line…"
                : "Pick a namespace and pod, then start the tail."}
            </p>
          ) : (
            <ul className="space-y-0.5">
              {lines.map((line) => (
                <li key={line.id} className="flex items-start gap-2">
                  <LevelBadge level={levelOf(line.text)} />
                  <span className="whitespace-pre-wrap break-all text-content-primary">{line.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
