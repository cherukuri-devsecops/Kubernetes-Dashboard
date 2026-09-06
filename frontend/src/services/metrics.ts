import { apiFetch } from "@/api/client";

export type SeriesPoint = {
  time: string;
  value: number;
};

export type ClusterMetrics = {
  cpuCores: number;
  cpuTotalCores: number;
  memoryBytes: number;
  memoryTotalBytes: number;
  networkRxBytesPerSec: number;
  networkTxBytesPerSec: number;
  diskUsedBytes: number;
  diskTotalBytes: number;
};

export type ClusterMetricsRange = {
  cpu: SeriesPoint[];
  memory: SeriesPoint[];
  networkRx: SeriesPoint[];
  networkTx: SeriesPoint[];
  diskRead: SeriesPoint[];
  diskWrite: SeriesPoint[];
};

export type NodeMetric = {
  name: string;
  cpuPercent: number;
  memoryPercent: number;
  memoryBytes: number;
  memoryTotalBytes: number;
  networkRxBytesPerSec: number;
  networkTxBytesPerSec: number;
  diskPercent: number;
  diskUsedBytes: number;
  diskTotalBytes: number;
};

export type NodeMetricsRange = {
  cpu: SeriesPoint[];
  memory: SeriesPoint[];
  networkRx: SeriesPoint[];
  networkTx: SeriesPoint[];
  diskRead: SeriesPoint[];
  diskWrite: SeriesPoint[];
};

export type NamespaceMetric = {
  namespace: string;
  cpuCores: number;
  memoryBytes: number;
  networkRxBytesPerSec: number;
  networkTxBytesPerSec: number;
};

export type NamespaceMetricsRange = {
  cpu: SeriesPoint[];
  memory: SeriesPoint[];
  networkRx: SeriesPoint[];
  networkTx: SeriesPoint[];
};

export type PodMetric = {
  pod: string;
  cpuCores: number;
  memoryBytes: number;
  networkRxBytesPerSec: number;
  networkTxBytesPerSec: number;
};

export type PodMetricsRange = {
  cpu: SeriesPoint[];
  memory: SeriesPoint[];
  networkRx: SeriesPoint[];
  networkTx: SeriesPoint[];
};

export const fetchClusterMetrics = () => apiFetch<ClusterMetrics>("/api/metrics/cluster");

export const fetchClusterMetricsRange = (rangeMinutes: number, stepSeconds: number) =>
  apiFetch<ClusterMetricsRange>(
    `/api/metrics/cluster/range?rangeMinutes=${rangeMinutes}&stepSeconds=${stepSeconds}`,
  );

export const fetchNodeMetrics = () => apiFetch<NodeMetric[]>("/api/metrics/nodes");

export const fetchNodeMetricsRange = (node: string, rangeMinutes: number, stepSeconds: number) =>
  apiFetch<NodeMetricsRange>(
    `/api/metrics/nodes/range?node=${encodeURIComponent(node)}&rangeMinutes=${rangeMinutes}&stepSeconds=${stepSeconds}`,
  );

export const fetchNamespaceMetrics = () => apiFetch<NamespaceMetric[]>("/api/metrics/namespaces");

export const fetchNamespaceMetricsRange = (namespace: string, rangeMinutes: number, stepSeconds: number) =>
  apiFetch<NamespaceMetricsRange>(
    `/api/metrics/namespaces/range?namespace=${encodeURIComponent(namespace)}&rangeMinutes=${rangeMinutes}&stepSeconds=${stepSeconds}`,
  );

export const fetchPodMetrics = (namespace: string) =>
  apiFetch<PodMetric[]>(`/api/metrics/pods?namespace=${encodeURIComponent(namespace)}`);

export const fetchPodMetricsRange = (namespace: string, pod: string, rangeMinutes: number, stepSeconds: number) =>
  apiFetch<PodMetricsRange>(
    `/api/metrics/pods/range?namespace=${encodeURIComponent(namespace)}&pod=${encodeURIComponent(pod)}&rangeMinutes=${rangeMinutes}&stepSeconds=${stepSeconds}`,
  );
