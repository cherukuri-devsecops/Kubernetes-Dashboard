import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import { ChartCard, metricColors } from "@/components/charts/ChartCard";
import { LineMetricChart, type LinePoint } from "@/components/charts/LineMetricChart";
import { BarMetricChart, type BarPoint } from "@/components/charts/BarMetricChart";
import { GaugeChart } from "@/components/charts/GaugeChart";
import { HeatmapGrid, type HeatmapColumn, type HeatmapRow } from "@/components/charts/HeatmapGrid";
import {
  fetchClusterMetrics,
  fetchClusterMetricsRange,
  fetchNodeMetrics,
  fetchNodeMetricsRange,
  fetchNamespaceMetrics,
  fetchNamespaceMetricsRange,
  fetchPodMetrics,
  fetchPodMetricsRange,
  type ClusterMetrics,
  type NodeMetric,
  type NamespaceMetric,
  type PodMetric,
  type SeriesPoint,
} from "@/services/metrics";
import { fetchNamespaces, type K8sNamespace } from "@/services/kubernetes";

const TIME_RANGES = ["1h", "6h", "24h", "7d"] as const;
type TimeRange = (typeof TIME_RANGES)[number];

const RANGE_SETTINGS: Record<TimeRange, { rangeMinutes: number; stepSeconds: number }> = {
  "1h": { rangeMinutes: 60, stepSeconds: 30 },
  "6h": { rangeMinutes: 360, stepSeconds: 120 },
  "24h": { rangeMinutes: 1440, stepSeconds: 300 },
  "7d": { rangeMinutes: 10080, stepSeconds: 1800 },
};

const REFRESH_INTERVAL_MS = 30000;

const SCOPE_TABS = [
  { key: "cluster", label: "Cluster" },
  { key: "node", label: "Node" },
  { key: "namespace", label: "Namespace" },
  { key: "pod", label: "Pod" },
] as const;
type ScopeTab = (typeof SCOPE_TABS)[number]["key"];

function formatTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function bytesToGiB(bytes: number): number {
  return Math.round((bytes / 1024 ** 3) * 100) / 100;
}

function bytesPerSecToMBps(bytes: number): number {
  return Math.round((bytes / 1024 ** 2) * 100) / 100;
}

function toLineSeries(points: SeriesPoint[], transform: (v: number) => number = (v) => v): LinePoint[] {
  return points.map((p) => ({ time: formatTime(Number(p.time)), value: Math.round(transform(p.value) * 1000) / 1000 }));
}

function toBarSeries(a: SeriesPoint[], b: SeriesPoint[], transform: (v: number) => number = (v) => v): BarPoint[] {
  const bByTime = new Map(b.map((p) => [String(p.time), p.value]));
  return a.map((p) => ({
    time: formatTime(Number(p.time)),
    a: Math.round(transform(p.value) * 100) / 100,
    b: Math.round(transform(bByTime.get(String(p.time)) ?? 0) * 100) / 100,
  }));
}

type MetricSummaryRow = { key: string; label: string; color: string; unit: string; series: LinePoint[] };

function summarize(series: LinePoint[]): { current: number; avg: number; min: number; max: number } | null {
  if (series.length === 0) return null;
  const values = series.map((p) => p.value);
  const sum = values.reduce((acc, v) => acc + v, 0);
  return {
    current: values[values.length - 1],
    avg: Math.round((sum / values.length) * 1000) / 1000,
    min: Math.min(...values),
    max: Math.max(...values),
  };
}

function MetricSummaryTable({ rows }: { rows: MetricSummaryRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h3 className="mb-3 text-sm font-medium text-content-primary">Summary</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
              <th className="py-2 pr-4 font-medium">Metric</th>
              <th className="py-2 pr-4 font-medium">Current</th>
              <th className="py-2 pr-4 font-medium">Avg</th>
              <th className="py-2 pr-4 font-medium">Min</th>
              <th className="py-2 pr-4 font-medium">Max</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => {
              const stats = summarize(row.series);
              return (
                <tr key={row.key}>
                  <td className="py-2 pr-4 text-content-primary">
                    <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} />
                    {row.label}
                  </td>
                  <td className="py-2 pr-4 text-content-secondary">{stats ? `${stats.current}${row.unit}` : "—"}</td>
                  <td className="py-2 pr-4 text-content-secondary">{stats ? `${stats.avg}${row.unit}` : "—"}</td>
                  <td className="py-2 pr-4 text-content-secondary">{stats ? `${stats.min}${row.unit}` : "—"}</td>
                  <td className="py-2 pr-4 text-content-secondary">{stats ? `${stats.max}${row.unit}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const selectClass = "h-9 rounded-md border border-line bg-surface-hover/60 px-2 text-sm text-content-secondary outline-none";

function RangeSelector({ range, onChange }: { range: TimeRange; onChange: (range: TimeRange) => void }) {
  return (
    <div className="flex items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
      {TIME_RANGES.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={clsx(
            "h-8 rounded px-3 text-sm transition",
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

function DiskUnavailableNote() {
  return (
    <div className="rounded-lg border border-line bg-surface-hover/40 p-4 text-sm text-content-muted">
      Disk metrics aren't available at this scope in this cluster — the container runtime only reports
      filesystem usage at the node level.
    </div>
  );
}

function ClusterTab({ range }: { range: TimeRange }) {
  const [cluster, setCluster] = useState<ClusterMetrics | null>(null);
  const [cpuSeries, setCpuSeries] = useState<LinePoint[]>([]);
  const [memorySeries, setMemorySeries] = useState<LinePoint[]>([]);
  const [networkSeries, setNetworkSeries] = useState<BarPoint[]>([]);
  const [diskSeries, setDiskSeries] = useState<BarPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const rangeSettings = useMemo(() => RANGE_SETTINGS[range], [range]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [instant, series] = await Promise.all([
          fetchClusterMetrics(),
          fetchClusterMetricsRange(rangeSettings.rangeMinutes, rangeSettings.stepSeconds),
        ]);
        if (cancelled) return;
        setCluster(instant);
        setCpuSeries(toLineSeries(series.cpu));
        setMemorySeries(toLineSeries(series.memory, bytesToGiB));
        setNetworkSeries(toBarSeries(series.networkRx, series.networkTx, bytesPerSecToMBps));
        setDiskSeries(toBarSeries(series.diskRead, series.diskWrite, bytesPerSecToMBps));
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load metrics");
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [rangeSettings]);

  const cpuPercent = cluster && cluster.cpuTotalCores ? (cluster.cpuCores / cluster.cpuTotalCores) * 100 : 0;
  const memoryPercent = cluster && cluster.memoryTotalBytes ? (cluster.memoryBytes / cluster.memoryTotalBytes) * 100 : 0;
  const diskPercent = cluster && cluster.diskTotalBytes ? (cluster.diskUsedBytes / cluster.diskTotalBytes) * 100 : 0;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-signal-red/30 bg-signal-red/5 p-4 text-sm text-signal-red">
          Prometheus is unavailable: {error}
        </div>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-3">
        <GaugeChart
          value={cpuPercent}
          color={metricColors.cpu}
          label="CPU"
          sublabel={cluster ? `${cluster.cpuCores.toFixed(2)} / ${cluster.cpuTotalCores.toFixed(0)} cores` : undefined}
        />
        <GaugeChart
          value={memoryPercent}
          color={metricColors.memory}
          label="Memory"
          sublabel={cluster ? `${bytesToGiB(cluster.memoryBytes)} / ${bytesToGiB(cluster.memoryTotalBytes)} GiB` : undefined}
        />
        <GaugeChart
          value={diskPercent}
          color={metricColors.disk}
          label="Disk"
          sublabel={cluster ? `${bytesToGiB(cluster.diskUsedBytes)} / ${bytesToGiB(cluster.diskTotalBytes)} GiB` : undefined}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="CPU usage" subtitle={`Last ${range}, sum across pods`}>
          <LineMetricChart color={metricColors.cpu} unit=" cores" series={cpuSeries} label="CPU" />
        </ChartCard>
        <ChartCard title="Memory usage" subtitle={`Last ${range}, sum across pods`}>
          <LineMetricChart color={metricColors.memory} unit=" GiB" series={memorySeries} label="Memory" />
        </ChartCard>
        <ChartCard title="Network throughput" subtitle={`Last ${range}, cluster-wide`}>
          <BarMetricChart color={metricColors.network} unit=" MB/s" series={networkSeries} labelA="Receive" labelB="Transmit" />
        </ChartCard>
        <ChartCard title="Disk I/O" subtitle={`Last ${range}, cluster-wide`}>
          <BarMetricChart color={metricColors.disk} unit=" MB/s" series={diskSeries} labelA="Read" labelB="Write" />
        </ChartCard>
      </section>

      <MetricSummaryTable
        rows={[
          { key: "cpu", label: "CPU", color: metricColors.cpu, unit: " cores", series: cpuSeries },
          { key: "memory", label: "Memory", color: metricColors.memory, unit: " GiB", series: memorySeries },
        ]}
      />
    </div>
  );
}

function NodeTab({ range }: { range: TimeRange }) {
  const [nodes, setNodes] = useState<NodeMetric[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [cpuSeries, setCpuSeries] = useState<LinePoint[]>([]);
  const [memorySeries, setMemorySeries] = useState<LinePoint[]>([]);
  const [networkSeries, setNetworkSeries] = useState<BarPoint[]>([]);
  const [diskSeries, setDiskSeries] = useState<BarPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const rangeSettings = useMemo(() => RANGE_SETTINGS[range], [range]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchNodeMetrics();
        if (cancelled) return;
        setNodes(data);
        setSelected((current) => current || data[0]?.name || "");
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load node metrics");
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;

    async function load() {
      try {
        const series = await fetchNodeMetricsRange(selected, rangeSettings.rangeMinutes, rangeSettings.stepSeconds);
        if (cancelled) return;
        setCpuSeries(toLineSeries(series.cpu, (v) => v * 100));
        setMemorySeries(toLineSeries(series.memory, bytesToGiB));
        setNetworkSeries(toBarSeries(series.networkRx, series.networkTx, bytesPerSecToMBps));
        setDiskSeries(toBarSeries(series.diskRead, series.diskWrite, bytesPerSecToMBps));
      } catch {
        // charts just keep their last-known state
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selected, rangeSettings]);

  const node = nodes.find((n) => n.name === selected) ?? null;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-signal-red/30 bg-signal-red/5 p-4 text-sm text-signal-red">{error}</div>
      ) : null}

      <div className="flex items-center gap-2">
        <select value={selected} onChange={(event) => setSelected(event.target.value)} className={selectClass}>
          {nodes.map((n) => (
            <option key={n.name} value={n.name}>
              {n.name}
            </option>
          ))}
        </select>
      </div>

      {node ? (
        <section className="grid gap-4 sm:grid-cols-3">
          <GaugeChart value={node.cpuPercent} color={metricColors.cpu} label="CPU" />
          <GaugeChart
            value={node.memoryPercent}
            color={metricColors.memory}
            label="Memory"
            sublabel={`${bytesToGiB(node.memoryBytes)} / ${bytesToGiB(node.memoryTotalBytes)} GiB`}
          />
          <GaugeChart
            value={node.diskPercent}
            color={metricColors.disk}
            label="Disk"
            sublabel={`${bytesToGiB(node.diskUsedBytes)} / ${bytesToGiB(node.diskTotalBytes)} GiB`}
          />
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="CPU usage" subtitle={`Last ${range}, ${selected || "—"}`}>
          <LineMetricChart color={metricColors.cpu} unit="%" series={cpuSeries} label="CPU" />
        </ChartCard>
        <ChartCard title="Memory usage" subtitle={`Last ${range}, ${selected || "—"}`}>
          <LineMetricChart color={metricColors.memory} unit=" GiB" series={memorySeries} label="Memory" />
        </ChartCard>
        <ChartCard title="Network throughput" subtitle={`Last ${range}, ${selected || "—"}`}>
          <BarMetricChart color={metricColors.network} unit=" MB/s" series={networkSeries} labelA="Receive" labelB="Transmit" />
        </ChartCard>
        <ChartCard title="Disk I/O" subtitle={`Last ${range}, ${selected || "—"}`}>
          <BarMetricChart color={metricColors.disk} unit=" MB/s" series={diskSeries} labelA="Read" labelB="Write" />
        </ChartCard>
      </section>

      <MetricSummaryTable
        rows={[
          { key: "cpu", label: "CPU", color: metricColors.cpu, unit: "%", series: cpuSeries },
          { key: "memory", label: "Memory", color: metricColors.memory, unit: " GiB", series: memorySeries },
        ]}
      />

      <section className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">All nodes</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
                <th className="py-2 pr-4 font-medium">Node</th>
                <th className="py-2 pr-4 font-medium">CPU</th>
                <th className="py-2 pr-4 font-medium">Memory</th>
                <th className="py-2 pr-4 font-medium">Disk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {nodes.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-content-muted">
                    No node metrics available.
                  </td>
                </tr>
              ) : (
                nodes.map((n) => (
                  <tr key={n.name} onClick={() => setSelected(n.name)} className="cursor-pointer hover:bg-surface-hover/60">
                    <td className="py-2.5 pr-4 text-content-primary">{n.name}</td>
                    <td className="py-2.5 pr-4 text-content-secondary">{n.cpuPercent}%</td>
                    <td className="py-2.5 pr-4 text-content-secondary">{n.memoryPercent}%</td>
                    <td className="py-2.5 pr-4 text-content-secondary">{n.diskPercent}%</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

const NAMESPACE_HEATMAP_COLUMNS: HeatmapColumn[] = [
  { key: "cpu", label: "CPU (cores)", color: metricColors.cpu, format: (v) => v.toFixed(3) },
  { key: "memory", label: "Memory (GiB)", color: metricColors.memory, format: (v) => bytesToGiB(v).toFixed(2) },
  { key: "network", label: "Network (MB/s)", color: metricColors.network, format: (v) => bytesPerSecToMBps(v).toFixed(2) },
];

function NamespaceTab({ range }: { range: TimeRange }) {
  const [namespaces, setNamespaces] = useState<NamespaceMetric[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [cpuSeries, setCpuSeries] = useState<LinePoint[]>([]);
  const [memorySeries, setMemorySeries] = useState<LinePoint[]>([]);
  const [networkSeries, setNetworkSeries] = useState<BarPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const rangeSettings = useMemo(() => RANGE_SETTINGS[range], [range]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchNamespaceMetrics();
        if (cancelled) return;
        setNamespaces(data);
        setSelected((current) => current || data[0]?.namespace || "");
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load namespace metrics");
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;

    async function load() {
      try {
        const series = await fetchNamespaceMetricsRange(selected, rangeSettings.rangeMinutes, rangeSettings.stepSeconds);
        if (cancelled) return;
        setCpuSeries(toLineSeries(series.cpu));
        setMemorySeries(toLineSeries(series.memory, bytesToGiB));
        setNetworkSeries(toBarSeries(series.networkRx, series.networkTx, bytesPerSecToMBps));
      } catch {
        // charts just keep their last-known state
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selected, rangeSettings]);

  const rows: HeatmapRow[] = namespaces.map((n) => ({
    key: n.namespace,
    label: n.namespace,
    values: { cpu: n.cpuCores, memory: n.memoryBytes, network: n.networkRxBytesPerSec + n.networkTxBytesPerSec },
  }));

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-signal-red/30 bg-signal-red/5 p-4 text-sm text-signal-red">{error}</div>
      ) : null}

      <section className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">Namespaces</h3>
        <p className="mb-3 text-xs text-content-muted">Click a row to view its detail charts below.</p>
        <HeatmapGrid columns={NAMESPACE_HEATMAP_COLUMNS} rows={rows} selectedKey={selected} onSelectRow={setSelected} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="CPU usage" subtitle={`Last ${range}, ${selected || "—"}`}>
          <LineMetricChart color={metricColors.cpu} unit=" cores" series={cpuSeries} label="CPU" />
        </ChartCard>
        <ChartCard title="Memory usage" subtitle={`Last ${range}, ${selected || "—"}`}>
          <LineMetricChart color={metricColors.memory} unit=" GiB" series={memorySeries} label="Memory" />
        </ChartCard>
        <ChartCard title="Network throughput" subtitle={`Last ${range}, ${selected || "—"}`}>
          <BarMetricChart color={metricColors.network} unit=" MB/s" series={networkSeries} labelA="Receive" labelB="Transmit" />
        </ChartCard>
        <DiskUnavailableNote />
      </section>

      <MetricSummaryTable
        rows={[
          { key: "cpu", label: "CPU", color: metricColors.cpu, unit: " cores", series: cpuSeries },
          { key: "memory", label: "Memory", color: metricColors.memory, unit: " GiB", series: memorySeries },
        ]}
      />
    </div>
  );
}

const POD_HEATMAP_COLUMNS: HeatmapColumn[] = [
  { key: "cpu", label: "CPU (cores)", color: metricColors.cpu, format: (v) => v.toFixed(3) },
  { key: "memory", label: "Memory (MiB)", color: metricColors.memory, format: (v) => Math.round(v / 1024 ** 2).toString() },
  { key: "network", label: "Network (KB/s)", color: metricColors.network, format: (v) => Math.round(v / 1024).toString() },
];

function PodTab({ range }: { range: TimeRange }) {
  const [namespaces, setNamespaces] = useState<K8sNamespace[]>([]);
  const [namespace, setNamespace] = useState<string>("");
  const [pods, setPods] = useState<PodMetric[]>([]);
  const [selectedPod, setSelectedPod] = useState<string>("");
  const [cpuSeries, setCpuSeries] = useState<LinePoint[]>([]);
  const [memorySeries, setMemorySeries] = useState<LinePoint[]>([]);
  const [networkSeries, setNetworkSeries] = useState<BarPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const rangeSettings = useMemo(() => RANGE_SETTINGS[range], [range]);

  useEffect(() => {
    let cancelled = false;
    fetchNamespaces()
      .then((data) => {
        if (cancelled) return;
        setNamespaces(data);
        setNamespace((current) => current || data[0]?.name || "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!namespace) return;
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchPodMetrics(namespace);
        if (cancelled) return;
        setPods(data);
        setSelectedPod((current) => (data.some((p) => p.pod === current) ? current : data[0]?.pod || ""));
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load pod metrics");
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [namespace]);

  useEffect(() => {
    if (!namespace || !selectedPod) return;
    let cancelled = false;

    async function load() {
      try {
        const series = await fetchPodMetricsRange(namespace, selectedPod, rangeSettings.rangeMinutes, rangeSettings.stepSeconds);
        if (cancelled) return;
        setCpuSeries(toLineSeries(series.cpu));
        setMemorySeries(toLineSeries(series.memory, (v) => v / 1024 ** 2));
        setNetworkSeries(toBarSeries(series.networkRx, series.networkTx, (v) => v / 1024));
      } catch {
        // charts just keep their last-known state
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [namespace, selectedPod, rangeSettings]);

  const rows: HeatmapRow[] = pods.map((p) => ({
    key: p.pod,
    label: p.pod,
    values: { cpu: p.cpuCores, memory: p.memoryBytes, network: p.networkRxBytesPerSec + p.networkTxBytesPerSec },
  }));

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <div className="rounded-lg border border-signal-red/30 bg-signal-red/5 p-4 text-sm text-signal-red">{error}</div>
      ) : null}

      <div className="flex items-center gap-2">
        <select
          value={namespace}
          onChange={(event) => {
            setNamespace(event.target.value);
            setSelectedPod("");
          }}
          className={selectClass}
        >
          {namespaces.map((ns) => (
            <option key={ns.name} value={ns.name}>
              {ns.name}
            </option>
          ))}
        </select>
      </div>

      <section className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">Pods in {namespace || "—"}</h3>
        <p className="mb-3 text-xs text-content-muted">Click a row to view its detail charts below.</p>
        <HeatmapGrid columns={POD_HEATMAP_COLUMNS} rows={rows} selectedKey={selectedPod} onSelectRow={setSelectedPod} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="CPU usage" subtitle={`Last ${range}, ${selectedPod || "—"}`}>
          <LineMetricChart color={metricColors.cpu} unit=" cores" series={cpuSeries} label="CPU" />
        </ChartCard>
        <ChartCard title="Memory usage" subtitle={`Last ${range}, ${selectedPod || "—"}`}>
          <LineMetricChart color={metricColors.memory} unit=" MiB" series={memorySeries} label="Memory" />
        </ChartCard>
        <ChartCard title="Network throughput" subtitle={`Last ${range}, ${selectedPod || "—"}`}>
          <BarMetricChart color={metricColors.network} unit=" KB/s" series={networkSeries} labelA="Receive" labelB="Transmit" />
        </ChartCard>
        <DiskUnavailableNote />
      </section>

      <MetricSummaryTable
        rows={[
          { key: "cpu", label: "CPU", color: metricColors.cpu, unit: " cores", series: cpuSeries },
          { key: "memory", label: "Memory", color: metricColors.memory, unit: " MiB", series: memorySeries },
        ]}
      />
    </div>
  );
}

export function MetricsPage() {
  const [scope, setScope] = useState<ScopeTab>("cluster");
  const [range, setRange] = useState<TimeRange>("1h");

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5 shadow-panel sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-brand-400">Metrics</p>
          <h2 className="mt-1 text-xl font-semibold text-content-primary">Resource usage</h2>
          <p className="mt-1 text-sm text-content-muted">Live CPU, memory, network, and disk usage from Prometheus.</p>
        </div>
        <RangeSelector range={range} onChange={setRange} />
      </section>

      <div className="flex items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
        {SCOPE_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setScope(tab.key)}
            className={clsx(
              "h-9 rounded px-3 text-sm transition",
              scope === tab.key
                ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                : "text-content-muted hover:text-content-primary",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {scope === "cluster" ? <ClusterTab range={range} /> : null}
      {scope === "node" ? <NodeTab range={range} /> : null}
      {scope === "namespace" ? <NamespaceTab range={range} /> : null}
      {scope === "pod" ? <PodTab range={range} /> : null}
    </div>
  );
}
