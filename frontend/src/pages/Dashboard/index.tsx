import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Gauge as GaugeIcon,
  RefreshCw,
  ScrollText,
  Send,
  Server,
  Sparkles,
  User,
  X,
} from "lucide-react";
import clsx from "clsx";

import { ChartCard, chartAxisColor, chartGridColor, chartTooltipContentStyle, chartTooltipLabelStyle } from "@/components/charts/ChartCard";
import { GaugeChart } from "@/components/charts/GaugeChart";
import { DonutChart, type DonutSegment } from "@/components/charts/DonutChart";
import { Sparkline, type SparklinePoint } from "@/components/charts/Sparkline";
import { AlertStatusBadge, SeverityBadge } from "@/components/common/badges";
import { fetchClusterInfo, fetchNamespaces, fetchPods, fetchServices, type ClusterInfo, type K8sPod } from "@/services/kubernetes";
import { fetchClusterMetrics, fetchClusterMetricsRange, fetchPodMetrics, type ClusterMetrics } from "@/services/metrics";
import { searchLogs, type LogEntry } from "@/services/logs";
import { formatDuration, generateAlerts, generateTraces, getCannedReply, type AlertItem, type Trace } from "@/utils/mockData";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const REFRESH_INTERVAL_MS = 30000;
const LOG_REFRESH_INTERVAL_MS = 10000;

const TIME_RANGES = ["15m", "1h", "6h", "24h"] as const;
type TimeRange = (typeof TIME_RANGES)[number];
const RANGE_SETTINGS: Record<TimeRange, { rangeMinutes: number; stepSeconds: number }> = {
  "15m": { rangeMinutes: 15, stepSeconds: 15 },
  "1h": { rangeMinutes: 60, stepSeconds: 60 },
  "6h": { rangeMinutes: 360, stepSeconds: 300 },
  "24h": { rangeMinutes: 1440, stepSeconds: 900 },
};

function formatTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function bytesToGiB(bytes: number): number {
  return Math.round((bytes / 1024 ** 3) * 100) / 100;
}

function hashSeed(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return hash;
}

function seededRange(seed: string, min: number, max: number): number {
  return min + (hashSeed(seed) % (max - min));
}

type PodUsage = { pod: string; namespace: string; cpuCores: number; memoryBytes: number };

type SectionCardProps = { title: string; action?: ReactNode; children: ReactNode; className?: string };
function SectionCard({ title, action, children, className }: SectionCardProps) {
  return (
    <section className={clsx("rounded-lg border border-line bg-surface p-4", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-content-primary">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function RangeSelector({ range, onChange }: { range: TimeRange; onChange: (range: TimeRange) => void }) {
  return (
    <div className="flex items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
      {TIME_RANGES.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={clsx(
            "h-7 rounded px-2.5 text-xs transition",
            range === option
              ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
              : "text-content-muted hover:text-content-primary",
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const [range, setRange] = useState<TimeRange>("15m");
  const rangeSettings = useMemo(() => RANGE_SETTINGS[range], [range]);

  const [clusterInfo, setClusterInfo] = useState<ClusterInfo | null>(null);
  const [clusterMetrics, setClusterMetrics] = useState<ClusterMetrics | null>(null);
  const [cpuSeries, setCpuSeries] = useState<SparklinePoint[]>([]);
  const [memorySeries, setMemorySeries] = useState<SparklinePoint[]>([]);
  const [pods, setPods] = useState<K8sPod[]>([]);
  const [topCpuPods, setTopCpuPods] = useState<PodUsage[]>([]);
  const [topMemoryPods, setTopMemoryPods] = useState<PodUsage[]>([]);
  const [services, setServices] = useState<{ name: string; namespace: string }[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const alerts = useMemo<AlertItem[]>(() => generateAlerts(), []);
  const traces = useMemo<Trace[]>(() => generateTraces().slice(0, 5), []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [info, cluster, range_, allPods, namespaces, svcs] = await Promise.all([
          fetchClusterInfo(),
          fetchClusterMetrics(),
          fetchClusterMetricsRange(rangeSettings.rangeMinutes, rangeSettings.stepSeconds),
          fetchPods(null),
          fetchNamespaces(),
          fetchServices(null).catch(() => []),
        ]);
        if (cancelled) return;

        setClusterInfo(info);
        setClusterMetrics(cluster);
        setPods(allPods);
        setServices(svcs.slice(0, 5).map((s) => ({ name: s.name, namespace: s.namespace })));
        setCpuSeries(range_.cpu.map((p) => ({ time: formatTime(Number(p.time)), value: Math.round(p.value * 1000) / 1000 })));
        setMemorySeries(range_.memory.map((p) => ({ time: formatTime(Number(p.time)), value: bytesToGiB(p.value) })));

        const perNamespacePods = await Promise.all(
          namespaces.map((ns) =>
            fetchPodMetrics(ns.name)
              .then((list) => list.map((p): PodUsage => ({ pod: p.pod, namespace: ns.name, cpuCores: p.cpuCores, memoryBytes: p.memoryBytes })))
              .catch(() => [] as PodUsage[]),
          ),
        );
        if (cancelled) return;
        const flattened = perNamespacePods.flat();
        setTopCpuPods([...flattened].sort((a, b) => b.cpuCores - a.cpuCores).slice(0, 5));
        setTopMemoryPods([...flattened].sort((a, b) => b.memoryBytes - a.memoryBytes).slice(0, 5));
      } catch {
        // stat tiles/charts just show their empty/last-known state
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
  }, [rangeSettings]);

  useEffect(() => {
    let cancelled = false;

    async function loadLogs() {
      try {
        const { entries } = await searchLogs({ rangeMinutes: 15, limit: 6 });
        if (!cancelled) setLogs(entries);
      } catch {
        // preview panel just stays empty
      }
    }

    loadLogs();
    const id = window.setInterval(loadLogs, LOG_REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const podCounts = useMemo(() => {
    const running = pods.filter((p) => p.status === "Running" || p.status === "Succeeded").length;
    const pending = pods.filter((p) => p.status === "Pending").length;
    const failed = pods.filter((p) => p.status === "Failed" || p.status === "Unknown").length;
    return { total: pods.length, running, pending, failed };
  }, [pods]);

  const cpuPercent = clusterMetrics && clusterMetrics.cpuTotalCores ? (clusterMetrics.cpuCores / clusterMetrics.cpuTotalCores) * 100 : 0;
  const memoryPercent = clusterMetrics && clusterMetrics.memoryTotalBytes ? (clusterMetrics.memoryBytes / clusterMetrics.memoryTotalBytes) * 100 : 0;
  const diskPercent = clusterMetrics && clusterMetrics.diskTotalBytes ? (clusterMetrics.diskUsedBytes / clusterMetrics.diskTotalBytes) * 100 : 0;
  const podHealthPercent = podCounts.total > 0 ? (podCounts.running / podCounts.total) * 100 : 0;

  const nodeHealthPercent = clusterInfo && clusterInfo.nodeCount > 0 ? Math.round((clusterInfo.readyNodeCount / clusterInfo.nodeCount) * 100) : null;

  const firingAlerts = alerts.filter((a) => a.status === "firing");
  const criticalAlerts = alerts.filter((a) => a.severity === "critical" && a.status !== "resolved");
  const warningAlerts = alerts.filter((a) => a.severity === "warning" && a.status !== "resolved");

  const podStatusSegments: DonutSegment[] = [
    { key: "running", label: "Running", value: podCounts.running, color: "#31d0aa" },
    { key: "pending", label: "Pending", value: podCounts.pending, color: "#f5c66a" },
    { key: "failed", label: "Failed", value: podCounts.failed, color: "#ff6b6b" },
  ];

  const alertSeveritySegments: DonutSegment[] = [
    { key: "critical", label: "Critical", value: criticalAlerts.length, color: "#ff6b6b" },
    { key: "warning", label: "Warning", value: warningAlerts.length, color: "#f5c66a" },
    { key: "info", label: "Info", value: alerts.filter((a) => a.severity === "info" && a.status !== "resolved").length, color: "#6ea8fe" },
  ];

  const aiInsights = [...criticalAlerts, ...warningAlerts].slice(0, 3);

  const events = useMemo(() => {
    const sourcePods = pods.length > 0 ? pods.slice(0, 5) : [];
    const templates = [
      { type: "Warning" as const, reason: "BackOff", message: "Back-off restarting failed container" },
      { type: "Normal" as const, reason: "Pulled", message: "Successfully pulled image" },
      { type: "Normal" as const, reason: "Scheduled", message: "Successfully assigned to node" },
      { type: "Normal" as const, reason: "Created", message: "Created container" },
      { type: "Warning" as const, reason: "Unhealthy", message: "Readiness probe failed" },
    ];
    if (sourcePods.length === 0) return [];
    return templates.map((tmpl, index) => {
      const pod = sourcePods[index % sourcePods.length];
      return {
        id: `${pod.namespace}/${pod.name}/${tmpl.reason}`,
        time: new Date(Date.now() - seededRange(`${pod.name}${tmpl.reason}`, 30, 900) * 1000),
        ...tmpl,
        object: `pod/${pod.name}`,
        namespace: pod.namespace,
      };
    });
  }, [pods]);

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4 xl:flex-row xl:items-start">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-content-primary">Cluster Overview</h2>
            <p className="text-xs text-content-muted">Live data from the connected Kubernetes cluster.</p>
          </div>
          <div className="flex items-center gap-2">
            <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && "animate-spin")} aria-hidden="true" />
            <RangeSelector range={range} onChange={setRange} />
          </div>
        </div>

        {/* Stat row */}
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">Cluster Health</span>
              <CheckCircle2 className={clsx("h-4 w-4", nodeHealthPercent === 100 ? "text-signal-green" : "text-signal-amber")} aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{nodeHealthPercent ?? "—"}%</p>
            <p className="mt-0.5 text-xs text-content-secondary">{nodeHealthPercent === 100 ? "Healthy" : "Degraded"}</p>
          </article>

          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">Nodes</span>
              <Server className="h-4 w-4 text-signal-blue" aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{clusterInfo?.nodeCount ?? "—"}</p>
            <p className="mt-0.5 text-xs text-content-secondary">
              Ready: {clusterInfo?.readyNodeCount ?? "—"}
              {clusterInfo && clusterInfo.nodeCount > clusterInfo.readyNodeCount ? (
                <span className="ml-2 text-signal-red">Not Ready: {clusterInfo.nodeCount - clusterInfo.readyNodeCount}</span>
              ) : null}
            </p>
          </article>

          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">Pods</span>
              <Boxes className="h-4 w-4 text-signal-green" aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{podCounts.total || "—"}</p>
            <p className="mt-0.5 text-xs text-content-secondary">
              Running: {podCounts.running}
              {podCounts.pending > 0 ? <span className="ml-2 text-signal-amber">Pending: {podCounts.pending}</span> : null}
              {podCounts.failed > 0 ? <span className="ml-2 text-signal-red">Failed: {podCounts.failed}</span> : null}
            </p>
          </article>

          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">CPU Usage</span>
              <Cpu className="h-4 w-4 text-signal-green" aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{cpuPercent ? `${cpuPercent.toFixed(0)}%` : "—"}</p>
            <div className="mt-1 h-8">
              <Sparkline data={cpuSeries.slice(-16)} color="#31d0aa" />
            </div>
            <p className="text-xs text-content-muted">
              {clusterMetrics ? `${clusterMetrics.cpuCores.toFixed(1)} / ${clusterMetrics.cpuTotalCores.toFixed(0)} cores` : "—"}
            </p>
          </article>

          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">Memory Usage</span>
              <GaugeIcon className="h-4 w-4 text-signal-blue" aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{memoryPercent ? `${memoryPercent.toFixed(0)}%` : "—"}</p>
            <div className="mt-1 h-8">
              <Sparkline data={memorySeries.slice(-16)} color="#6ea8fe" />
            </div>
            <p className="text-xs text-content-muted">
              {clusterMetrics ? `${bytesToGiB(clusterMetrics.memoryBytes)} / ${bytesToGiB(clusterMetrics.memoryTotalBytes)} GiB` : "—"}
            </p>
          </article>

          <article className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-content-muted">Alerts</span>
              <Bell className="h-4 w-4 text-signal-amber" aria-hidden="true" />
            </div>
            <p className="text-2xl font-semibold text-content-primary">{alerts.length}</p>
            <p className="mt-0.5 text-xs text-content-secondary">
              <span className="text-signal-red">Critical: {criticalAlerts.length}</span>
              <span className="ml-2 text-signal-amber">Warning: {warningAlerts.length}</span>
            </p>
            <Link to="/alerts" className="mt-2 flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary">
              View all alerts
              <ArrowRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          </article>
        </section>

        {/* Charts + top pods by CPU */}
        <section className="grid gap-4 xl:grid-cols-3">
          <ChartCard title="CPU Usage" subtitle={`Last ${range}, cluster-wide`}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={cpuSeries} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="overviewCpuGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#31d0aa" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#31d0aa" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={chartGridColor} vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={{ stroke: chartGridColor }} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={false} tickLine={false} unit=" cores" width={56} />
                <Tooltip contentStyle={chartTooltipContentStyle} labelStyle={chartTooltipLabelStyle} formatter={(value) => [`${value} cores`, "CPU"]} />
                <Area type="monotone" dataKey="value" stroke="#31d0aa" strokeWidth={2} fill="url(#overviewCpuGradient)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Memory Usage" subtitle={`Last ${range}, cluster-wide`}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={memorySeries} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="overviewMemGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6ea8fe" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#6ea8fe" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={chartGridColor} vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={{ stroke: chartGridColor }} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={false} tickLine={false} unit=" GiB" width={56} />
                <Tooltip contentStyle={chartTooltipContentStyle} labelStyle={chartTooltipLabelStyle} formatter={(value) => [`${value} GiB`, "Memory"]} />
                <Area type="monotone" dataKey="value" stroke="#6ea8fe" strokeWidth={2} fill="url(#overviewMemGradient)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <SectionCard title="Top Pods by CPU">
            <ul className="space-y-2.5">
              {topCpuPods.length === 0 ? (
                <li className="text-xs text-content-muted">No pod metrics available.</li>
              ) : (
                topCpuPods.map((p) => {
                  const max = topCpuPods[0]?.cpuCores || 1;
                  return (
                    <li key={`${p.namespace}/${p.pod}`} className="text-xs">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="truncate text-content-primary">{p.pod}</span>
                        <span className="shrink-0 text-content-muted">{p.cpuCores.toFixed(3)} cores</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface-hover">
                        <div className="h-1.5 rounded-full bg-signal-green" style={{ width: `${Math.max((p.cpuCores / max) * 100, 4)}%` }} />
                      </div>
                    </li>
                  );
                })
              )}
            </ul>
          </SectionCard>
        </section>

        {/* Top pods by memory, pod status, alerts by severity, recent alerts */}
        <section className="grid gap-4 xl:grid-cols-4">
          <SectionCard title="Top Pods by Memory">
            <ul className="space-y-2.5">
              {topMemoryPods.length === 0 ? (
                <li className="text-xs text-content-muted">No pod metrics available.</li>
              ) : (
                topMemoryPods.map((p) => {
                  const max = topMemoryPods[0]?.memoryBytes || 1;
                  return (
                    <li key={`${p.namespace}/${p.pod}`} className="text-xs">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="truncate text-content-primary">{p.pod}</span>
                        <span className="shrink-0 text-content-muted">{bytesToGiB(p.memoryBytes) < 1 ? `${Math.round(p.memoryBytes / 1024 ** 2)} MiB` : `${bytesToGiB(p.memoryBytes)} GiB`}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface-hover">
                        <div className="h-1.5 rounded-full bg-signal-blue" style={{ width: `${Math.max((p.memoryBytes / max) * 100, 4)}%` }} />
                      </div>
                    </li>
                  );
                })
              )}
            </ul>
          </SectionCard>

          <SectionCard title="Pod Status">
            <DonutChart segments={podStatusSegments} centerLabel="Total" />
          </SectionCard>

          <SectionCard title="Alerts by Severity">
            <DonutChart segments={alertSeveritySegments} centerLabel="Total" />
          </SectionCard>

          <SectionCard
            title="Recent Alerts"
            action={
              <Link to="/alerts" className="flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary">
                View all
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            }
          >
            <ul className="divide-y divide-line">
              {alerts.slice(0, 4).map((alert) => (
                <li key={alert.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="truncate text-xs text-content-primary">{alert.name}</p>
                    <p className="truncate text-[11px] text-content-muted">{alert.resource}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <SeverityBadge severity={alert.severity} />
                    <AlertStatusBadge status={alert.status} />
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>
        </section>

        {/* Logs, traces, events */}
        <section className="grid gap-4 xl:grid-cols-3">
          <SectionCard
            title="Logs (Loki)"
            action={
              <Link to="/logs" className="flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary">
                View all
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            }
          >
            <ul className="max-h-64 space-y-2 overflow-y-auto font-mono text-[11px]">
              {logs.length === 0 ? (
                <li className="text-content-muted">No recent log lines.</li>
              ) : (
                logs.map((log, index) => (
                  <li key={`${log.timestamp}-${index}`} className="flex items-start gap-1.5">
                    <span className="shrink-0 text-content-muted">{new Date(Number(log.timestamp) / 1_000_000).toLocaleTimeString()}</span>
                    <span className="shrink-0 text-content-secondary">{log.pod}</span>
                    <span className="truncate text-content-primary">{log.line}</span>
                  </li>
                ))
              )}
            </ul>
          </SectionCard>

          <SectionCard
            title="Traces (Tempo)"
            action={
              <Link to="/traces" className="flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary">
                View all
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            }
          >
            <ul className="space-y-2.5">
              {traces.map((trace) => (
                <li key={trace.id} className="text-xs">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="truncate text-content-primary">
                      {trace.rootService} <span className="text-content-muted">→ {trace.operation}</span>
                    </span>
                    <span className="shrink-0 text-content-muted">{formatDuration(trace.durationMs)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-hover">
                    <div
                      className={clsx("h-1.5 rounded-full", trace.status === "error" ? "bg-signal-red" : "bg-brand")}
                      style={{ width: `${Math.min((trace.durationMs / 1500) * 100, 100)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Events (Kubernetes)">
            <ul className="max-h-64 space-y-2 overflow-y-auto text-[11px]">
              {events.length === 0 ? (
                <li className="text-content-muted">No recent events.</li>
              ) : (
                events.map((event) => (
                  <li key={event.id} className="flex items-start gap-1.5">
                    <span className={clsx("mt-0.5 shrink-0 rounded px-1 text-[10px] font-semibold uppercase", event.type === "Warning" ? "bg-signal-amber/10 text-signal-amber" : "bg-surface-hover text-content-muted")}>
                      {event.type}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-content-secondary">
                      <span className="text-content-primary">{event.reason}</span> · {event.object} — {event.message}
                    </span>
                  </li>
                ))
              )}
            </ul>
          </SectionCard>
        </section>

        {/* Cluster resource overview, services, AI insights */}
        <section className="grid gap-4 xl:grid-cols-3">
          <SectionCard title="Cluster Resource Overview" className="xl:col-span-1">
            <div className="grid grid-cols-2 gap-2">
              <GaugeChart value={cpuPercent} color="#31d0aa" label="CPU" sublabel={clusterMetrics ? `${clusterMetrics.cpuCores.toFixed(1)} / ${clusterMetrics.cpuTotalCores.toFixed(0)} cores` : undefined} />
              <GaugeChart value={memoryPercent} color="#6ea8fe" label="Memory" sublabel={clusterMetrics ? `${bytesToGiB(clusterMetrics.memoryBytes)} / ${bytesToGiB(clusterMetrics.memoryTotalBytes)} GiB` : undefined} />
              <GaugeChart value={diskPercent} color="#d95926" label="Storage" sublabel={clusterMetrics ? `${bytesToGiB(clusterMetrics.diskUsedBytes)} / ${bytesToGiB(clusterMetrics.diskTotalBytes)} GiB` : undefined} />
              <GaugeChart value={podHealthPercent} color="#a78bfa" label="Pods" sublabel={`${podCounts.running} / ${podCounts.total} running`} />
            </div>
          </SectionCard>

          <SectionCard title="Top Services by Request Rate">
            <ul className="space-y-2.5">
              {services.length === 0 ? (
                <li className="text-xs text-content-muted">No services found.</li>
              ) : (
                services.map((svc) => {
                  const rate = seededRange(`${svc.namespace}/${svc.name}`, 20, 260);
                  const max = 260;
                  return (
                    <li key={`${svc.namespace}/${svc.name}`} className="text-xs">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="truncate text-content-primary">{svc.name}</span>
                        <span className="shrink-0 text-content-muted">{rate} req/s</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface-hover">
                        <div className="h-1.5 rounded-full bg-brand" style={{ width: `${(rate / max) * 100}%` }} />
                      </div>
                    </li>
                  );
                })
              )}
            </ul>
            <p className="mt-3 text-[11px] text-content-muted">Simulated — no service-mesh/ingress request-rate metrics wired up yet.</p>
          </SectionCard>

          <SectionCard title="AI Insights">
            <ul className="space-y-2.5">
              {aiInsights.length === 0 ? (
                <li className="text-xs text-content-muted">No active issues detected.</li>
              ) : (
                aiInsights.map((alert) => (
                  <li key={alert.id} className="flex items-start gap-2 rounded-md bg-surface-hover/60 p-2.5">
                    <AlertTriangle className={clsx("mt-0.5 h-3.5 w-3.5 shrink-0", alert.severity === "critical" ? "text-signal-red" : "text-signal-amber")} aria-hidden="true" />
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-content-primary">{alert.name}</p>
                      <p className="mt-0.5 text-[11px] text-content-muted">{alert.message}</p>
                    </div>
                  </li>
                ))
              )}
            </ul>
            <Link to="/ai" className="mt-3 flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary">
              View all insights
              <ArrowRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          </SectionCard>
        </section>

        <div className="flex items-center gap-2 text-xs text-content-muted">
          <ScrollText className="h-3.5 w-3.5" aria-hidden="true" />
          Alerts, traces, events, and request rates are simulated previews — Prometheus/Loki-backed panels above are live.
        </div>
      </div>

      <AssistantPanel />
    </div>
  );
}

type ChatMessage = { id: string; role: "assistant" | "user"; text: string };

const INITIAL_MESSAGES: ChatMessage[] = [
  { id: "welcome", role: "assistant", text: "Ask me about pods, CPU/memory, alerts, or logs across the cluster." },
];

function AssistantPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [visible, setVisible] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
    setInput("");
    setThinking(true);
    window.setTimeout(() => {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: getCannedReply(trimmed) }]);
      setThinking(false);
    }, 700);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(input);
  }

  if (!visible) {
    return (
      <div className="flex justify-end xl:sticky xl:top-20 xl:block xl:w-14 xl:shrink-0">
        <button
          type="button"
          onClick={() => setVisible(true)}
          title="Open AI Assistant"
          className="flex h-10 items-center gap-2 rounded-md border border-line bg-surface px-3 text-content-secondary transition hover:bg-surface-hover hover:text-content-primary xl:h-14 xl:w-14 xl:flex-col xl:justify-center xl:gap-1 xl:px-0 xl:text-[10px]"
        >
          <Bot className="h-4 w-4 text-brand-400" aria-hidden="true" />
          <span className="xl:text-[10px]">AI Assistant</span>
        </button>
      </div>
    );
  }

  return (
    <aside className="flex w-full shrink-0 flex-col rounded-lg border border-line bg-surface xl:sticky xl:top-20 xl:w-80">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <Sparkles className="h-4 w-4 text-brand-400" aria-hidden="true" />
        <h3 className="flex-1 text-sm font-medium text-content-primary">AI Assistant</h3>
        <button
          type="button"
          onClick={() => setMinimized((current) => !current)}
          title={minimized ? "Expand" : "Minimize"}
          className="grid h-6 w-6 place-items-center rounded text-content-muted transition hover:bg-surface-hover hover:text-content-primary"
        >
          {minimized ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
        </button>
        <button
          type="button"
          onClick={() => setVisible(false)}
          title="Close"
          className="grid h-6 w-6 place-items-center rounded text-content-muted transition hover:bg-surface-hover hover:text-content-primary"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      {!minimized ? (
        <>
          <div ref={scrollRef} className="flex h-80 flex-col gap-3 overflow-y-auto p-3 xl:h-[32rem]">
            {messages.map((message) => (
              <div key={message.id} className={clsx("flex items-start gap-2", message.role === "user" ? "flex-row-reverse" : "")}>
                <div className={clsx("grid h-6 w-6 shrink-0 place-items-center rounded-full", message.role === "assistant" ? "bg-brand/[0.16] text-brand-400" : "bg-surface-hover text-content-secondary")}>
                  {message.role === "assistant" ? <Bot className="h-3.5 w-3.5" aria-hidden="true" /> : <User className="h-3.5 w-3.5" aria-hidden="true" />}
                </div>
                <div className={clsx("max-w-[85%] rounded-lg px-3 py-2 text-xs leading-5", message.role === "assistant" ? "bg-surface-hover text-content-primary" : "bg-brand/[0.16] text-content-primary")}>
                  {message.text}
                </div>
              </div>
            ))}
            {thinking ? (
              <div className="flex items-center gap-2">
                <div className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand/[0.16] text-brand-400">
                  <Bot className="h-3.5 w-3.5" aria-hidden="true" />
                </div>
                <div className="flex items-center gap-1 rounded-lg bg-surface-hover px-3 py-2">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted" />
                </div>
              </div>
            ) : null}
          </div>

          <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-line p-3">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask anything…"
              className="h-9 flex-1 rounded-md border border-line bg-surface-hover/60 px-2.5 text-xs text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-brand text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </form>
        </>
      ) : null}
    </aside>
  );
}
