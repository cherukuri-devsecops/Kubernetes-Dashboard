import { useEffect, useMemo, useState } from "react";
import { KeyRound, RefreshCw, Search, Server, ShieldCheck, Users } from "lucide-react";
import clsx from "clsx";

import { StatTile } from "@/components/cards/StatTile";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { SegmentedTabs } from "@/components/common/SegmentedTabs";
import { AccessBadge, Pill, ScopeBadge, SubjectKindBadge } from "@/components/common/badges";
import {
  fetchRoleBindings,
  fetchRoles,
  fetchServiceAccounts,
  fetchSubjects,
  type RbacRole,
  type RbacSubject,
  type RoleBinding,
  type ServiceAccount,
} from "@/services/rbac";
import { fetchClusterInfo, fetchNodes, type ClusterInfo, type K8sNode } from "@/services/kubernetes";
import { formatRelativeTime, parseDate } from "@/utils/format";

type ViewTab = "subjects" | "roles" | "bindings" | "serviceAccounts" | "cluster";

const REFRESH_INTERVAL_MS = 60000;

const searchInputClass =
  "h-8 w-full rounded-md border border-line bg-surface-hover/60 pl-8 pr-2.5 text-xs text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20";

function FilterBar({
  value,
  onChange,
  placeholder,
  hideDefaults,
  onToggleDefaults,
  summary,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  hideDefaults: boolean;
  onToggleDefaults: () => void;
  summary: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3">
      <div className="relative min-w-[240px] flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-muted" aria-hidden="true" />
        <input
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className={searchInputClass}
        />
      </div>
      <label className="flex items-center gap-2 text-xs text-content-muted">
        <input type="checkbox" checked={hideDefaults} onChange={onToggleDefaults} className="accent-brand" />
        Hide built-in system: entries
      </label>
      <span className="text-xs text-content-muted">{summary}</span>
    </div>
  );
}

export function AdminPage() {
  const [tab, setTab] = useState<ViewTab>("subjects");
  const [query, setQuery] = useState("");
  const [hideDefaults, setHideDefaults] = useState(true);

  const [subjects, setSubjects] = useState<RbacSubject[]>([]);
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [bindings, setBindings] = useState<RoleBinding[]>([]);
  const [accounts, setAccounts] = useState<ServiceAccount[]>([]);
  const [clusterInfo, setClusterInfo] = useState<ClusterInfo | null>(null);
  const [nodes, setNodes] = useState<K8sNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [subjectList, roleList, bindingList, accountList, info, nodeList] = await Promise.all([
          fetchSubjects(),
          fetchRoles(),
          fetchRoleBindings(),
          fetchServiceAccounts(),
          fetchClusterInfo(),
          fetchNodes(),
        ]);
        if (cancelled) return;
        setSubjects(subjectList);
        setRoles(roleList);
        setBindings(bindingList);
        setAccounts(accountList);
        setClusterInfo(info);
        setNodes(nodeList);
        setError(null);
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not load cluster RBAC");
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
  }, []);

  const needle = query.trim().toLowerCase();

  const filteredSubjects = useMemo(
    () =>
      subjects.filter(
        (subject) =>
          (!hideDefaults || !subject.isDefault) &&
          (!needle || subject.name.toLowerCase().includes(needle) || subject.kind.toLowerCase().includes(needle)),
      ),
    [subjects, hideDefaults, needle],
  );

  const filteredRoles = useMemo(
    () =>
      roles.filter(
        (role) =>
          (!hideDefaults || !role.isDefault) &&
          (!needle || role.name.toLowerCase().includes(needle) || role.resources.some((r) => r.includes(needle))),
      ),
    [roles, hideDefaults, needle],
  );

  const filteredBindings = useMemo(
    () =>
      bindings.filter(
        (binding) =>
          (!hideDefaults || !binding.isDefault) &&
          (!needle ||
            binding.name.toLowerCase().includes(needle) ||
            binding.roleName.toLowerCase().includes(needle) ||
            binding.subjects.some((subject) => subject.name.toLowerCase().includes(needle))),
      ),
    [bindings, hideDefaults, needle],
  );

  const filteredAccounts = useMemo(
    () =>
      accounts.filter(
        (account) =>
          !needle || account.name.toLowerCase().includes(needle) || account.namespace.toLowerCase().includes(needle),
      ),
    [accounts, needle],
  );

  const counts = useMemo(
    () => ({
      subjects: subjects.filter((subject) => !subject.isDefault).length,
      clusterWide: subjects.filter((subject) => !subject.isDefault && subject.clusterWide).length,
      accounts: accounts.length,
      roles: roles.filter((role) => !role.isDefault).length,
    }),
    [subjects, accounts, roles],
  );

  const subjectColumns: Column<RbacSubject>[] = [
    { key: "kind", header: "Kind", render: (subject) => <SubjectKindBadge kind={subject.kind} /> },
    { key: "name", header: "Name", cellClassName: "text-content-primary", render: (subject) => subject.name },
    { key: "namespace", header: "Namespace", render: (subject) => subject.namespace ?? "—" },
    {
      key: "roles",
      header: "Roles",
      render: (subject) => (
        <span className="line-clamp-1 max-w-sm">{subject.roles.map((role) => role.role).join(", ")}</span>
      ),
    },
    { key: "count", header: "Bindings", render: (subject) => subject.roleCount },
    {
      key: "scope",
      header: "Scope",
      render: (subject) => <ScopeBadge scope={subject.clusterWide ? "Cluster" : subject.namespaces[0] ?? "—"} />,
    },
  ];

  const roleColumns: Column<RbacRole>[] = [
    { key: "name", header: "Role", cellClassName: "text-content-primary", render: (role) => role.name },
    { key: "kind", header: "Kind", render: (role) => <Pill label={role.kind} /> },
    { key: "scope", header: "Scope", render: (role) => <ScopeBadge scope={role.scope} /> },
    { key: "rules", header: "Rules", render: (role) => role.ruleCount },
    { key: "access", header: "Access", render: (role) => <AccessBadge access={role.access} /> },
    {
      key: "resources",
      header: "Resources",
      render: (role) => <span className="line-clamp-1 max-w-md text-xs">{role.resources.join(", ") || "—"}</span>,
    },
  ];

  const bindingColumns: Column<RoleBinding>[] = [
    { key: "name", header: "Binding", cellClassName: "text-content-primary", render: (binding) => binding.name },
    { key: "kind", header: "Kind", render: (binding) => <Pill label={binding.kind} /> },
    { key: "role", header: "Role", render: (binding) => `${binding.roleKind}/${binding.roleName}` },
    {
      key: "subjects",
      header: "Subjects",
      render: (binding) => (
        <span className="line-clamp-1 max-w-sm">
          {binding.subjects.map((subject) => `${subject.kind}:${subject.name}`).join(", ") || "—"}
        </span>
      ),
    },
    { key: "scope", header: "Scope", render: (binding) => <ScopeBadge scope={binding.scope} /> },
  ];

  const accountColumns: Column<ServiceAccount>[] = [
    { key: "name", header: "Service Account", cellClassName: "text-content-primary", render: (account) => account.name },
    { key: "namespace", header: "Namespace", render: (account) => account.namespace },
    { key: "secrets", header: "Secrets", render: (account) => account.secrets.length },
    {
      key: "automount",
      header: "Automount token",
      render: (account) => <Pill label={account.automountToken ? "yes" : "no"} tone={account.automountToken ? "amber" : "green"} />,
    },
    {
      key: "created",
      header: "Created",
      render: (account) => (account.createdAt ? formatRelativeTime(parseDate(account.createdAt)) : "—"),
    },
  ];

  const nodeColumns: Column<K8sNode>[] = [
    { key: "name", header: "Node", cellClassName: "text-content-primary", render: (node) => node.name },
    {
      key: "status",
      header: "Status",
      render: (node) => <Pill label={node.status} tone={node.status === "Ready" ? "green" : "red"} />,
    },
    { key: "roles", header: "Roles", render: (node) => node.roles.join(", ") },
    { key: "version", header: "Kubelet", render: (node) => node.kubeletVersion ?? "—" },
    { key: "ip", header: "Internal IP", render: (node) => node.internalIp ?? "—" },
    { key: "cpu", header: "CPU", render: (node) => node.cpuCapacity ?? "—" },
    { key: "memory", header: "Memory", render: (node) => node.memoryCapacity ?? "—" },
    { key: "pods", header: "Pod capacity", render: (node) => node.podCapacity ?? "—" },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Administration</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Cluster access &amp; identity</h2>
          <p className="mt-0.5 text-xs text-content-muted">
            Read live from the cluster's RBAC. Kubernetes has no User object — an identity exists here because a
            RoleBinding grants it access.
          </p>
        </div>
        <RefreshCw className={clsx("h-3.5 w-3.5 text-content-muted", loading && "animate-spin")} aria-hidden="true" />
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Non-system Subjects" value={counts.subjects} icon={Users} tone="violet" />
        <StatTile
          label="Cluster-wide Access"
          value={counts.clusterWide}
          icon={ShieldCheck}
          tone={counts.clusterWide > 0 ? "amber" : "green"}
        />
        <StatTile label="Service Accounts" value={counts.accounts} icon={KeyRound} tone="blue" />
        <StatTile label="Custom Roles" value={counts.roles} icon={Server} tone="neutral" />
      </section>

      <SegmentedTabs
        value={tab}
        onChange={setTab}
        options={[
          { key: "subjects", label: "Subjects", count: filteredSubjects.length },
          { key: "roles", label: "Roles & RBAC", count: filteredRoles.length },
          { key: "bindings", label: "Bindings", count: filteredBindings.length },
          { key: "serviceAccounts", label: "Service Accounts", count: filteredAccounts.length },
          { key: "cluster", label: "Cluster", count: nodes.length },
        ]}
      />

      {tab === "cluster" ? (
        <>
          <section className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="rounded-lg border border-line bg-surface p-4">
              <h3 className="mb-3 text-sm font-medium text-content-primary">Connected Cluster</h3>
              {clusterInfo ? (
                <dl className="space-y-2.5 text-xs">
                  <Detail label="Kubernetes version" value={clusterInfo.gitVersion} />
                  <Detail label="Platform" value={clusterInfo.platform} />
                  <Detail label="Nodes" value={`${clusterInfo.readyNodeCount} / ${clusterInfo.nodeCount} ready`} />
                  <Detail label="Namespaces" value={String(clusterInfo.namespaceCount)} />
                  <Detail label="Pods" value={String(clusterInfo.podCount)} />
                </dl>
              ) : (
                <p className="text-xs text-content-muted">{loading ? "Loading…" : "Cluster info unavailable."}</p>
              )}
            </div>
            <DataTable
              columns={nodeColumns}
              rows={nodes}
              rowKey={(node) => node.name}
              emptyMessage={loading ? "Loading nodes…" : "No nodes found."}
              minWidth={900}
            />
          </section>
        </>
      ) : (
        <>
          <FilterBar
            value={query}
            onChange={setQuery}
            hideDefaults={hideDefaults}
            onToggleDefaults={() => setHideDefaults((current) => !current)}
            placeholder={
              tab === "subjects"
                ? "Filter by subject name or kind…"
                : tab === "roles"
                  ? "Filter by role name or resource…"
                  : tab === "bindings"
                    ? "Filter by binding, role, or subject…"
                    : "Filter by service account or namespace…"
            }
            summary={
              tab === "subjects"
                ? `${filteredSubjects.length} of ${subjects.length} subjects`
                : tab === "roles"
                  ? `${filteredRoles.length} of ${roles.length} roles`
                  : tab === "bindings"
                    ? `${filteredBindings.length} of ${bindings.length} bindings`
                    : `${filteredAccounts.length} of ${accounts.length} service accounts`
            }
          />

          {tab === "subjects" ? (
            <DataTable
              columns={subjectColumns}
              rows={filteredSubjects}
              rowKey={(subject) => subject.id}
              emptyMessage={loading ? "Loading subjects…" : "No RBAC subjects match the current filters."}
              minWidth={900}
            />
          ) : null}

          {tab === "roles" ? (
            <DataTable
              columns={roleColumns}
              rows={filteredRoles}
              rowKey={(role) => `${role.kind}/${role.namespace ?? ""}/${role.name}`}
              emptyMessage={loading ? "Loading roles…" : "No roles match the current filters."}
              minWidth={960}
            />
          ) : null}

          {tab === "bindings" ? (
            <DataTable
              columns={bindingColumns}
              rows={filteredBindings}
              rowKey={(binding) => `${binding.kind}/${binding.namespace ?? ""}/${binding.name}`}
              emptyMessage={loading ? "Loading bindings…" : "No bindings match the current filters."}
              minWidth={960}
            />
          ) : null}

          {tab === "serviceAccounts" ? (
            <DataTable
              columns={accountColumns}
              rows={filteredAccounts}
              rowKey={(account) => `${account.namespace}/${account.name}`}
              emptyMessage={loading ? "Loading service accounts…" : "No service accounts match the current filters."}
              minWidth={860}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-content-muted">{label}</dt>
      <dd className="text-right text-content-primary">{value}</dd>
    </div>
  );
}
