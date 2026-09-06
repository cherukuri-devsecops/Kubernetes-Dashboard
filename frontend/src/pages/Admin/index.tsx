import { useMemo, useState, type FormEvent } from "react";
import { Ban, KeyRound, Search, Server, ShieldCheck, UserCheck, UserPlus, Users } from "lucide-react";
import clsx from "clsx";

import { StatTile } from "@/components/cards/StatTile";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { SegmentedTabs } from "@/components/common/SegmentedTabs";
import {
  AuditResultBadge,
  ClusterStatusBadge,
  Pill,
  RoleBadge,
  UserStatusBadge,
  type PillTone,
} from "@/components/common/badges";
import { Field, Modal, modalInputClass } from "@/components/modals/Modal";
import { formatRelativeFuture, formatRelativeTime } from "@/utils/mockData";
import {
  PERMISSION_RESOURCES,
  generateAuditLog,
  generateClusters,
  generateIntegrations,
  generateServiceAccounts,
  generateUsers,
  roleDefinitions,
  type AdminUser,
  type AuditEntry,
  type Integration,
  type PermissionLevel,
  type ServiceAccountToken,
  type UserRole,
} from "@/utils/mockAdmin";

type ViewTab = "users" | "roles" | "clusters" | "serviceAccounts" | "integrations" | "audit";

const TABS: { key: ViewTab; label: string }[] = [
  { key: "users", label: "Users" },
  { key: "roles", label: "Roles & RBAC" },
  { key: "clusters", label: "Clusters" },
  { key: "serviceAccounts", label: "Service Accounts" },
  { key: "integrations", label: "Integrations" },
  { key: "audit", label: "Audit Log" },
];

const PERMISSION_TONES: Record<PermissionLevel, PillTone> = {
  admin: "violet",
  write: "blue",
  read: "green",
  none: "neutral",
};

const PROVIDER_LABELS: Record<AdminUser["provider"], string> = {
  local: "Local (JWT)",
  google: "Google OAuth",
  oidc: "OIDC",
};

const ROLE_OPTIONS: UserRole[] = ["admin", "operator", "developer", "viewer"];

export function AdminPage() {
  const [tab, setTab] = useState<ViewTab>("users");
  const [users, setUsers] = useState<AdminUser[]>(() => generateUsers());
  const [serviceAccounts, setServiceAccounts] = useState<ServiceAccountToken[]>(() => generateServiceAccounts());
  const [integrations, setIntegrations] = useState<Integration[]>(() => generateIntegrations());
  const [inviteOpen, setInviteOpen] = useState(false);
  const [userQuery, setUserQuery] = useState("");
  const [auditQuery, setAuditQuery] = useState("");

  const clusters = useMemo(() => generateClusters(), []);
  const auditLog = useMemo<AuditEntry[]>(() => generateAuditLog(), []);

  const filteredUsers = useMemo(() => {
    const needle = userQuery.trim().toLowerCase();
    if (!needle) return users;
    return users.filter(
      (user) => user.name.toLowerCase().includes(needle) || user.email.toLowerCase().includes(needle) || user.role.includes(needle),
    );
  }, [users, userQuery]);

  const filteredAudit = useMemo(() => {
    const needle = auditQuery.trim().toLowerCase();
    if (!needle) return auditLog;
    return auditLog.filter(
      (entry) =>
        entry.actor.toLowerCase().includes(needle) ||
        entry.action.toLowerCase().includes(needle) ||
        entry.target.toLowerCase().includes(needle),
    );
  }, [auditLog, auditQuery]);

  const counts = useMemo(
    () => ({
      activeUsers: users.filter((user) => user.status === "active").length,
      admins: users.filter((user) => user.role === "admin").length,
      clusters: clusters.filter((cluster) => cluster.status === "connected").length,
      tokens: serviceAccounts.length,
    }),
    [users, clusters, serviceAccounts],
  );

  function toggleUserStatus(id: string) {
    setUsers((current) =>
      current.map((user) =>
        user.id === id ? { ...user, status: user.status === "disabled" ? "active" : "disabled" } : user,
      ),
    );
  }

  function inviteUser(name: string, email: string, role: UserRole, namespaces: string) {
    setUsers((current) => [
      {
        id: `usr-${Date.now()}`,
        name,
        email,
        role,
        provider: "oidc",
        status: "invited",
        namespaces: namespaces
          .split(",")
          .map((entry) => entry.trim())
          .filter(Boolean),
        lastLogin: null,
      },
      ...current,
    ]);
    setInviteOpen(false);
  }

  function revokeToken(id: string) {
    setServiceAccounts((current) => current.filter((token) => token.id !== id));
  }

  function toggleIntegration(id: string) {
    setIntegrations((current) =>
      current.map((integration) =>
        integration.id === id ? { ...integration, connected: !integration.connected } : integration,
      ),
    );
  }

  const userColumns: Column<AdminUser>[] = [
    {
      key: "user",
      header: "User",
      cellClassName: "text-content-primary",
      render: (user) => (
        <div>
          <p>{user.name}</p>
          <p className="text-[11px] text-content-muted">{user.email}</p>
        </div>
      ),
    },
    { key: "role", header: "Role", render: (user) => <RoleBadge role={user.role} /> },
    { key: "provider", header: "Provider", render: (user) => PROVIDER_LABELS[user.provider] },
    {
      key: "namespaces",
      header: "Namespaces",
      render: (user) => (user.namespaces.includes("*") ? "All namespaces" : user.namespaces.join(", ")),
    },
    { key: "status", header: "Status", render: (user) => <UserStatusBadge status={user.status} /> },
    { key: "lastLogin", header: "Last login", render: (user) => (user.lastLogin ? formatRelativeTime(user.lastLogin) : "never") },
    {
      key: "actions",
      header: "",
      render: (user) => (
        <button
          type="button"
          onClick={() => toggleUserStatus(user.id)}
          className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
        >
          {user.status === "disabled" ? (
            <>
              <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Enable
            </>
          ) : (
            <>
              <Ban className="h-3.5 w-3.5" aria-hidden="true" />
              Disable
            </>
          )}
        </button>
      ),
    },
  ];

  const tokenColumns: Column<ServiceAccountToken>[] = [
    { key: "name", header: "Service account", cellClassName: "text-content-primary", render: (token) => token.name },
    { key: "namespace", header: "Namespace", render: (token) => token.namespace },
    {
      key: "scopes",
      header: "Scopes",
      render: (token) => (
        <span className="flex flex-wrap gap-1">
          {token.scopes.map((scope) => (
            <span key={scope} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-content-muted">
              {scope}
            </span>
          ))}
        </span>
      ),
    },
    { key: "createdAt", header: "Created", render: (token) => formatRelativeTime(token.createdAt) },
    { key: "lastUsed", header: "Last used", render: (token) => (token.lastUsed ? formatRelativeTime(token.lastUsed) : "never") },
    {
      key: "expiresAt",
      header: "Expires",
      render: (token) => {
        if (!token.expiresAt) return "never";
        const expired = token.expiresAt.getTime() < Date.now();
        return (
          <span className={clsx(expired && "text-signal-red")}>
            {expired ? "expired" : formatRelativeFuture(token.expiresAt)}
          </span>
        );
      },
    },
    {
      key: "actions",
      header: "",
      render: (token) => (
        <button
          type="button"
          onClick={() => revokeToken(token.id)}
          className="rounded-md border border-line px-2 py-1 text-xs text-content-secondary transition hover:bg-signal-red/10 hover:text-signal-red"
        >
          Revoke
        </button>
      ),
    },
  ];

  const auditColumns: Column<AuditEntry>[] = [
    { key: "at", header: "Time", render: (entry) => formatRelativeTime(entry.at) },
    { key: "actor", header: "Actor", cellClassName: "text-content-primary", render: (entry) => entry.actor },
    { key: "action", header: "Action", cellClassName: "font-mono text-xs", render: (entry) => entry.action },
    { key: "target", header: "Target", render: (entry) => entry.target },
    { key: "ip", header: "Source IP", cellClassName: "font-mono text-xs", render: (entry) => entry.ip },
    { key: "result", header: "Result", render: (entry) => <AuditResultBadge result={entry.result} /> },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Administration</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Users, access, and clusters</h2>
        </div>
        {tab === "users" ? (
          <button
            type="button"
            onClick={() => setInviteOpen(true)}
            className="flex h-8 items-center gap-1.5 rounded-md bg-brand px-3 text-xs font-medium text-white transition hover:bg-brand-600"
          >
            <UserPlus className="h-3.5 w-3.5" aria-hidden="true" />
            Invite user
          </button>
        ) : null}
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Active Users" value={counts.activeUsers} icon={Users} tone="neutral" />
        <StatTile label="Administrators" value={counts.admins} icon={ShieldCheck} tone="violet" />
        <StatTile label="Connected Clusters" value={counts.clusters} icon={Server} tone="green" />
        <StatTile label="Service Account Tokens" value={counts.tokens} icon={KeyRound} tone="blue" />
      </section>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3">
        <SegmentedTabs options={TABS} value={tab} onChange={setTab} size="sm" />

        {tab === "users" ? <SearchInput value={userQuery} onChange={setUserQuery} placeholder="Search users by name, email, or role…" /> : null}
        {tab === "audit" ? <SearchInput value={auditQuery} onChange={setAuditQuery} placeholder="Search audit log by actor, action, or target…" /> : null}
      </div>

      {tab === "users" ? (
        <DataTable
          columns={userColumns}
          rows={filteredUsers}
          rowKey={(user) => user.id}
          emptyMessage="No users match the search."
          minWidth={1000}
        />
      ) : null}

      {tab === "roles" ? <RolesPanel users={users} /> : null}

      {tab === "clusters" ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {clusters.map((cluster) => (
            <article key={cluster.id} className="rounded-lg border border-line bg-surface p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium text-content-primary">{cluster.name}</h3>
                <ClusterStatusBadge status={cluster.status} />
              </div>
              <p className="truncate font-mono text-[11px] text-content-muted" title={cluster.endpoint}>
                {cluster.endpoint}
              </p>
              <dl className="mt-3 space-y-1.5 text-xs">
                <Row label="Environment" value={cluster.environment} />
                <Row label="Version" value={cluster.version} />
                <Row label="Nodes" value={String(cluster.nodes)} />
                <Row label="Last sync" value={formatRelativeTime(cluster.lastSync)} />
              </dl>
            </article>
          ))}
        </section>
      ) : null}

      {tab === "serviceAccounts" ? (
        <DataTable
          columns={tokenColumns}
          rows={serviceAccounts}
          rowKey={(token) => token.id}
          emptyMessage="No service account tokens."
          minWidth={1100}
        />
      ) : null}

      {tab === "integrations" ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {integrations.map((integration) => {
            const Icon = integration.icon;
            return (
              <article key={integration.id} className="flex flex-col rounded-lg border border-line bg-surface p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-md bg-surface-hover text-content-secondary">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-content-primary">{integration.name}</h3>
                      <p className="text-xs text-content-muted">{integration.category}</p>
                    </div>
                  </div>
                  <Pill
                    label={integration.connected ? "connected" : "not connected"}
                    tone={integration.connected ? "green" : "neutral"}
                  />
                </div>
                <p className="text-xs leading-5 text-content-secondary">{integration.description}</p>
                <p className="mt-2 truncate font-mono text-[11px] text-content-muted" title={integration.target}>
                  {integration.target}
                </p>
                <button
                  type="button"
                  onClick={() => toggleIntegration(integration.id)}
                  className={clsx(
                    "mt-4 h-8 rounded-md border text-xs transition",
                    integration.connected
                      ? "border-line text-content-secondary hover:bg-signal-red/10 hover:text-signal-red"
                      : "border-brand/40 bg-brand/10 text-brand-400 hover:bg-brand/20",
                  )}
                >
                  {integration.connected ? "Disconnect" : "Connect"}
                </button>
              </article>
            );
          })}
        </section>
      ) : null}

      {tab === "audit" ? (
        <DataTable
          columns={auditColumns}
          rows={filteredAudit}
          rowKey={(entry) => entry.id}
          emptyMessage="No audit entries match the search."
          minWidth={900}
        />
      ) : null}

      <InviteUserModal open={inviteOpen} onClose={() => setInviteOpen(false)} onSubmit={inviteUser} />
    </div>
  );
}

function RolesPanel({ users }: { users: AdminUser[] }) {
  const memberCounts = useMemo(() => {
    const counts = new Map<UserRole, number>();
    for (const user of users) counts.set(user.role, (counts.get(user.role) ?? 0) + 1);
    return counts;
  }, [users]);

  return (
    <div className="flex flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {roleDefinitions.map((role) => (
          <article key={role.key} className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-content-primary">{role.label}</h3>
              <RoleBadge role={role.key} />
            </div>
            <p className="text-xs leading-5 text-content-secondary">{role.description}</p>
            <p className="mt-3 text-xs text-content-muted">{memberCounts.get(role.key) ?? 0} members</p>
          </article>
        ))}
      </section>

      <section className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
              <th className="py-2 pl-4 pr-4 font-medium">Resource</th>
              {roleDefinitions.map((role) => (
                <th key={role.key} className="py-2 pr-4 font-medium">
                  {role.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {PERMISSION_RESOURCES.map((resource) => (
              <tr key={resource}>
                <td className="py-2.5 pl-4 pr-4 text-content-primary">{resource}</td>
                {roleDefinitions.map((role) => {
                  const level = role.permissions[resource] ?? "none";
                  return (
                    <td key={role.key} className="py-2.5 pr-4">
                      <Pill label={level} tone={PERMISSION_TONES[level]} className="capitalize" />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

type InviteUserModalProps = {
  open: boolean;
  onClose: () => void;
  onSubmit: (name: string, email: string, role: UserRole, namespaces: string) => void;
};

function InviteUserModal({ open, onClose, onSubmit }: InviteUserModalProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [namespaces, setNamespaces] = useState("default");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !email.trim()) return;
    onSubmit(name.trim(), email.trim(), role, namespaces);
    setName("");
    setEmail("");
    setRole("viewer");
    setNamespaces("default");
  }

  return (
    <Modal
      open={open}
      title="Invite user"
      description="The invite is sent through the configured identity provider."
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="h-8 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="invite-user-form"
            className="h-8 rounded-md bg-brand px-3 text-xs font-medium text-white transition hover:bg-brand-600"
          >
            Send invite
          </button>
        </>
      }
    >
      <form id="invite-user-form" onSubmit={handleSubmit} className="space-y-3">
        <Field label="Full name">
          <input type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ada Lovelace" className={modalInputClass} />
        </Field>
        <Field label="Email">
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ada@example.com" className={modalInputClass} />
        </Field>
        <Field label="Role">
          <select value={role} onChange={(event) => setRole(event.target.value as UserRole)} className={modalInputClass}>
            {ROLE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Namespaces" hint="Comma-separated. Use * for cluster-wide access.">
          <input type="text" value={namespaces} onChange={(event) => setNamespaces(event.target.value)} className={modalInputClass} />
        </Field>
      </form>
    </Modal>
  );
}

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <div className="relative min-w-[220px] flex-1">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-muted" aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-line bg-surface-hover/60 pl-8 pr-2.5 text-xs text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-content-muted">{label}</dt>
      <dd className="text-content-primary">{value}</dd>
    </div>
  );
}
