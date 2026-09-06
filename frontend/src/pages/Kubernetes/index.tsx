import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Boxes, Gauge, Layers, RefreshCw, Search, Server } from "lucide-react";
import clsx from "clsx";

import { StatTile } from "@/components/cards/StatTile";
import {
  fetchClusterInfo,
  fetchDaemonSets,
  fetchDeployments,
  fetchJobs,
  fetchNamespaces,
  fetchNodes,
  fetchPods,
  fetchPvcs,
  fetchServices,
  fetchStatefulSets,
  type ClusterInfo,
  type K8sDaemonSet,
  type K8sDeployment,
  type K8sJob,
  type K8sNamespace,
  type K8sNode,
  type K8sPod,
  type K8sPvc,
  type K8sService,
  type K8sStatefulSet,
} from "@/services/kubernetes";

type ResourceKind =
  | "nodes"
  | "namespaces"
  | "pods"
  | "deployments"
  | "services"
  | "statefulsets"
  | "daemonsets"
  | "jobs"
  | "pvcs";

const RESOURCE_TABS: { key: ResourceKind; label: string; namespaced: boolean }[] = [
  { key: "nodes", label: "Nodes", namespaced: false },
  { key: "namespaces", label: "Namespaces", namespaced: false },
  { key: "pods", label: "Pods", namespaced: true },
  { key: "deployments", label: "Deployments", namespaced: true },
  { key: "services", label: "Services", namespaced: true },
  { key: "statefulsets", label: "StatefulSets", namespaced: true },
  { key: "daemonsets", label: "DaemonSets", namespaced: true },
  { key: "jobs", label: "Jobs", namespaced: true },
  { key: "pvcs", label: "PVCs", namespaced: true },
];

const REFRESH_INTERVAL_MS = 15000;

function fetchTabData(tab: ResourceKind, namespace: string | null): Promise<unknown[]> {
  switch (tab) {
    case "nodes":
      return fetchNodes();
    case "namespaces":
      return fetchNamespaces();
    case "pods":
      return fetchPods(namespace);
    case "deployments":
      return fetchDeployments(namespace);
    case "services":
      return fetchServices(namespace);
    case "statefulsets":
      return fetchStatefulSets(namespace);
    case "daemonsets":
      return fetchDaemonSets(namespace);
    case "jobs":
      return fetchJobs(namespace);
    case "pvcs":
      return fetchPvcs(namespace);
  }
}

function formatAge(iso: string | null): string {
  if (!iso) return "—";
  const created = new Date(iso).getTime();
  const diffSec = Math.max(0, Math.round((Date.now() - created) / 1000));
  if (diffSec < 60) return `${diffSec}s`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h`;
  return `${Math.round(diffHour / 24)}d`;
}

function StatusPill({ label, tone }: { label: string; tone: "green" | "amber" | "red" | "neutral" }) {
  const styles = {
    green: "bg-signal-green/10 text-signal-green",
    amber: "bg-signal-amber/10 text-signal-amber",
    red: "bg-signal-red/10 text-signal-red",
    neutral: "bg-surface-hover text-content-secondary",
  } as const;
  return <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium", styles[tone])}>{label}</span>;
}

function podTone(status: string): "green" | "amber" | "red" | "neutral" {
  if (status === "Running" || status === "Succeeded") return "green";
  if (status === "Pending") return "amber";
  if (status === "Failed" || status === "Unknown") return "red";
  return "neutral";
}

type NamedRow = { name: string; namespace?: string };

function rowKey(row: unknown): string {
  const r = row as NamedRow;
  return r.namespace ? `${r.namespace}/${r.name}` : r.name;
}

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "—";
  return String(value);
}

function labelizeKey(key: string): string {
  const withSpaces = key.replace(/([A-Z])/g, " $1").toLowerCase();
  return withSpaces.charAt(0).toUpperCase() + withSpaces.slice(1);
}

function Th({ children }: { children: ReactNode }) {
  return <th className="py-2 pr-4 font-medium">{children}</th>;
}

function Td({ children }: { children: ReactNode }) {
  return <td className="py-2.5 pr-4 text-content-secondary">{children}</td>;
}

function EmptyRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-8 text-center text-content-muted">
        No resources found.
      </td>
    </tr>
  );
}

type ResourceTableProps = { tab: ResourceKind; rows: unknown[]; selectedKey: string | null; onSelectRow: (row: unknown) => void };

function ResourceTable({ tab, rows, selectedKey, onSelectRow }: ResourceTableProps) {
  function rowClass(item: unknown) {
    return clsx("cursor-pointer transition hover:bg-surface-hover", selectedKey === rowKey(item) && "bg-surface-hover");
  }

  if (tab === "nodes") {
    const items = rows as K8sNode[];
    return (
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Roles</Th>
            <Th>Version</Th>
            <Th>Internal IP</Th>
            <Th>CPU</Th>
            <Th>Memory</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={8} />}
          {items.map((node) => (
            <tr key={node.name} onClick={() => onSelectRow(node)} className={rowClass(node)}>
              <td className="py-2.5 pr-4 text-content-primary">{node.name}</td>
              <td className="py-2.5 pr-4">
                <StatusPill label={node.status} tone={node.status === "Ready" ? "green" : "red"} />
              </td>
              <Td>{node.roles.join(", ")}</Td>
              <Td>{node.kubeletVersion ?? "—"}</Td>
              <Td>{node.internalIp ?? "—"}</Td>
              <Td>
                {node.cpuAllocatable ?? "—"} / {node.cpuCapacity ?? "—"}
              </Td>
              <Td>
                {node.memoryAllocatable ?? "—"} / {node.memoryCapacity ?? "—"}
              </Td>
              <Td>{formatAge(node.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "namespaces") {
    const items = rows as K8sNamespace[];
    return (
      <table className="w-full min-w-[420px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Status</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={3} />}
          {items.map((ns) => (
            <tr key={ns.name} onClick={() => onSelectRow(ns)} className={rowClass(ns)}>
              <td className="py-2.5 pr-4 text-content-primary">{ns.name}</td>
              <td className="py-2.5 pr-4">
                <StatusPill label={ns.status} tone={ns.status === "Active" ? "green" : "amber"} />
              </td>
              <Td>{formatAge(ns.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "pods") {
    const items = rows as K8sPod[];
    return (
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Status</Th>
            <Th>Ready</Th>
            <Th>Restarts</Th>
            <Th>Node</Th>
            <Th>Pod IP</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={8} />}
          {items.map((pod) => (
            <tr key={`${pod.namespace}/${pod.name}`} onClick={() => onSelectRow(pod)} className={rowClass(pod)}>
              <td className="py-2.5 pr-4 text-content-primary">{pod.name}</td>
              <Td>{pod.namespace}</Td>
              <td className="py-2.5 pr-4">
                <StatusPill label={pod.status} tone={podTone(pod.status)} />
              </td>
              <Td>{pod.ready}</Td>
              <Td>{pod.restarts}</Td>
              <Td>{pod.node ?? "—"}</Td>
              <Td>{pod.podIp ?? "—"}</Td>
              <Td>{formatAge(pod.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "deployments") {
    const items = rows as K8sDeployment[];
    return (
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Ready</Th>
            <Th>Updated</Th>
            <Th>Available</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={6} />}
          {items.map((dep) => (
            <tr key={`${dep.namespace}/${dep.name}`} onClick={() => onSelectRow(dep)} className={rowClass(dep)}>
              <td className="py-2.5 pr-4 text-content-primary">{dep.name}</td>
              <Td>{dep.namespace}</Td>
              <td className="py-2.5 pr-4">
                <StatusPill
                  label={`${dep.readyReplicas}/${dep.replicas}`}
                  tone={dep.readyReplicas >= dep.replicas && dep.replicas > 0 ? "green" : "amber"}
                />
              </td>
              <Td>{dep.updatedReplicas}</Td>
              <Td>{dep.availableReplicas}</Td>
              <Td>{formatAge(dep.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "services") {
    const items = rows as K8sService[];
    return (
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Type</Th>
            <Th>Cluster IP</Th>
            <Th>Ports</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={6} />}
          {items.map((svc) => (
            <tr key={`${svc.namespace}/${svc.name}`} onClick={() => onSelectRow(svc)} className={rowClass(svc)}>
              <td className="py-2.5 pr-4 text-content-primary">{svc.name}</td>
              <Td>{svc.namespace}</Td>
              <Td>{svc.type}</Td>
              <Td>{svc.clusterIp ?? "—"}</Td>
              <Td>{svc.ports.join(", ") || "—"}</Td>
              <Td>{formatAge(svc.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "statefulsets") {
    const items = rows as K8sStatefulSet[];
    return (
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Ready</Th>
            <Th>Service</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={5} />}
          {items.map((sts) => (
            <tr key={`${sts.namespace}/${sts.name}`} onClick={() => onSelectRow(sts)} className={rowClass(sts)}>
              <td className="py-2.5 pr-4 text-content-primary">{sts.name}</td>
              <Td>{sts.namespace}</Td>
              <td className="py-2.5 pr-4">
                <StatusPill
                  label={`${sts.readyReplicas}/${sts.replicas}`}
                  tone={sts.readyReplicas >= sts.replicas && sts.replicas > 0 ? "green" : "amber"}
                />
              </td>
              <Td>{sts.serviceName ?? "—"}</Td>
              <Td>{formatAge(sts.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "daemonsets") {
    const items = rows as K8sDaemonSet[];
    return (
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Desired</Th>
            <Th>Ready</Th>
            <Th>Available</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={6} />}
          {items.map((ds) => (
            <tr key={`${ds.namespace}/${ds.name}`} onClick={() => onSelectRow(ds)} className={rowClass(ds)}>
              <td className="py-2.5 pr-4 text-content-primary">{ds.name}</td>
              <Td>{ds.namespace}</Td>
              <Td>{ds.desiredScheduled}</Td>
              <td className="py-2.5 pr-4">
                <StatusPill
                  label={`${ds.numberReady}/${ds.desiredScheduled}`}
                  tone={ds.numberReady >= ds.desiredScheduled && ds.desiredScheduled > 0 ? "green" : "amber"}
                />
              </td>
              <Td>{ds.numberAvailable}</Td>
              <Td>{formatAge(ds.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tab === "jobs") {
    const items = rows as K8sJob[];
    return (
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            <Th>Name</Th>
            <Th>Namespace</Th>
            <Th>Completions</Th>
            <Th>Succeeded</Th>
            <Th>Failed</Th>
            <Th>Active</Th>
            <Th>Age</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.length === 0 && <EmptyRow colSpan={7} />}
          {items.map((job) => (
            <tr key={`${job.namespace}/${job.name}`} onClick={() => onSelectRow(job)} className={rowClass(job)}>
              <td className="py-2.5 pr-4 text-content-primary">{job.name}</td>
              <Td>{job.namespace}</Td>
              <Td>{job.completions ?? "—"}</Td>
              <td className="py-2.5 pr-4">
                <StatusPill label={String(job.succeeded)} tone={job.succeeded > 0 ? "green" : "neutral"} />
              </td>
              <td className="py-2.5 pr-4">
                <StatusPill label={String(job.failed)} tone={job.failed > 0 ? "red" : "neutral"} />
              </td>
              <Td>{job.active}</Td>
              <Td>{formatAge(job.createdAt)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  const items = rows as K8sPvc[];
  return (
    <table className="w-full min-w-[720px] text-left text-sm">
      <thead>
        <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
          <Th>Name</Th>
          <Th>Namespace</Th>
          <Th>Status</Th>
          <Th>Volume</Th>
          <Th>Capacity</Th>
          <Th>Storage class</Th>
          <Th>Age</Th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {items.length === 0 && <EmptyRow colSpan={7} />}
        {items.map((pvc) => (
          <tr key={`${pvc.namespace}/${pvc.name}`} onClick={() => onSelectRow(pvc)} className={rowClass(pvc)}>
            <td className="py-2.5 pr-4 text-content-primary">{pvc.name}</td>
            <Td>{pvc.namespace}</Td>
            <td className="py-2.5 pr-4">
              <StatusPill label={pvc.status} tone={pvc.status === "Bound" ? "green" : "amber"} />
            </td>
            <Td>{pvc.volumeName ?? "—"}</Td>
            <Td>{pvc.capacity ?? "—"}</Td>
            <Td>{pvc.storageClass ?? "—"}</Td>
            <Td>{formatAge(pvc.createdAt)}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function KubernetesPage() {
  const [tab, setTab] = useState<ResourceKind>("pods");
  const [namespace, setNamespace] = useState<string>("");
  const [namespaces, setNamespaces] = useState<K8sNamespace[]>([]);
  const [clusterInfo, setClusterInfo] = useState<ClusterInfo | null>(null);
  const [clusterError, setClusterError] = useState<string | null>(null);

  const [rows, setRows] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedRow, setSelectedRow] = useState<unknown>(null);

  const activeTab = useMemo(() => RESOURCE_TABS.find((item) => item.key === tab)!, [tab]);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      try {
        const [info, ns] = await Promise.all([fetchClusterInfo(), fetchNamespaces()]);
        if (cancelled) return;
        setClusterInfo(info);
        setNamespaces(ns);
        setClusterError(null);
      } catch (err) {
        if (cancelled) return;
        setClusterError(err instanceof Error ? err.message : "Failed to load cluster info");
      }
    }

    loadOverview();
    const id = window.setInterval(loadOverview, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const data = await fetchTabData(tab, activeTab.namespaced ? namespace || null : null);
        if (cancelled) return;
        setRows(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load resource");
        setRows([]);
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
  }, [tab, namespace, activeTab.namespaced]);

  useEffect(() => {
    setSelectedRow(null);
    setSearch("");
  }, [tab, namespace]);

  const filteredRows = useMemo(() => {
    if (!search.trim()) return rows;
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => rowKey(row).toLowerCase().includes(needle));
  }, [rows, search]);

  const selectedKind = tab.endsWith("s") ? tab.slice(0, -1) : tab;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section className="rounded-lg border border-line bg-surface p-5 shadow-panel">
        <p className="text-sm text-brand-400">Kubernetes</p>
        <h2 className="mt-1 text-xl font-semibold text-content-primary">Kubernetes Explorer</h2>
        <p className="mt-1 text-sm text-content-muted">Live resources read directly from the cluster API.</p>
      </section>

      {clusterError ? (
        <section className="flex items-start gap-3 rounded-lg border border-signal-red/30 bg-signal-red/5 p-4 text-sm text-signal-red">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">Kubernetes API is unavailable</p>
            <p className="mt-1 text-content-muted">{clusterError}</p>
          </div>
        </section>
      ) : (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Nodes ready"
            value={clusterInfo ? `${clusterInfo.readyNodeCount}/${clusterInfo.nodeCount}` : "—"}
            icon={Server}
            tone="green"
          />
          <StatTile label="Namespaces" value={clusterInfo?.namespaceCount ?? "—"} icon={Layers} tone="blue" />
          <StatTile label="Pods" value={clusterInfo?.podCount ?? "—"} icon={Boxes} tone="green" />
          <StatTile label="Server version" value={clusterInfo?.gitVersion ?? "—"} icon={Gauge} tone="neutral" />
        </section>
      )}

      <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {RESOURCE_TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={clsx(
                "h-8 rounded px-3 text-sm transition",
                tab === item.key
                  ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                  : "text-content-muted hover:text-content-primary",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-surface-hover/60 px-2.5 text-sm text-content-muted">
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search workloads…"
              className="w-36 bg-transparent text-content-primary outline-none placeholder:text-content-muted sm:w-48"
            />
          </div>
          {activeTab.namespaced && (
            <select
              value={namespace}
              onChange={(event) => setNamespace(event.target.value)}
              className="h-9 rounded-md border border-line bg-surface-hover/60 px-2 text-sm text-content-secondary outline-none"
            >
              <option value="">All namespaces</option>
              {namespaces.map((ns) => (
                <option key={ns.name} value={ns.name}>
                  {ns.name}
                </option>
              ))}
            </select>
          )}
          <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && "animate-spin")} aria-hidden="true" />
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-lg border border-line bg-surface p-4">
          {error ? (
            <div className="flex items-center gap-2 py-8 text-center text-sm text-signal-red">
              <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
              {error}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <ResourceTable
                tab={tab}
                rows={filteredRows}
                selectedKey={selectedRow ? rowKey(selectedRow) : null}
                onSelectRow={setSelectedRow}
              />
            </div>
          )}
        </div>

        <div className="rounded-lg border border-line bg-surface p-4">
          <h3 className="mb-3 text-sm font-medium capitalize text-content-primary">{selectedKind} Detail</h3>
          {selectedRow ? (
            <dl className="space-y-2.5 text-xs">
              {Object.entries(selectedRow as Record<string, unknown>).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-content-muted">{labelizeKey(key)}</dt>
                  <dd className="break-words text-content-primary">{formatDetailValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-content-muted">Select a resource row to see its details.</p>
          )}
        </div>
      </section>
    </div>
  );
}
