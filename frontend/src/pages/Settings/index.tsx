import { useEffect, useState } from "react";
import { Bell, Info, Server, UserRound } from "lucide-react";
import clsx from "clsx";

import { ThemeSwitcher } from "@/components/common/ThemeSwitcher";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { API_BASE_URL } from "@/api/client";
import { fetchClusterInfo, type ClusterInfo } from "@/services/kubernetes";

const APP_VERSION = "0.1.0";

type SettingsTab = "general" | "notifications" | "cluster";

const TABS: { id: SettingsTab; label: string; icon: typeof UserRound }[] = [
  { id: "general", label: "General", icon: UserRound },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "cluster", label: "Cluster", icon: Server },
];

function Toggle({ label, description, defaultChecked = false }: { label: string; description: string; defaultChecked?: boolean }) {
  const [checked, setChecked] = useState(defaultChecked);
  return (
    <label className="flex items-start justify-between gap-4 py-3">
      <span>
        <span className="block text-sm font-medium text-content-primary">{label}</span>
        <span className="block text-xs text-content-muted">{description}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => setChecked((value) => !value)}
        className={clsx(
          "relative h-6 w-11 shrink-0 rounded-full transition",
          checked ? "bg-brand" : "bg-surface-hover",
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition",
            checked ? "left-5" : "left-0.5",
          )}
        />
      </button>
    </label>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-line py-2.5 text-sm last:border-b-0">
      <span className="text-content-muted">{label}</span>
      <span className="text-content-primary">{value}</span>
    </div>
  );
}

function GeneralTab() {
  const { user, provider } = useAuth();
  const { theme, resolvedTheme } = useTheme();
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">General Settings</h3>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-content-secondary">Name</span>
            <input
              type="text"
              defaultValue={user?.name}
              className="h-11 w-full rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-content-secondary">Email</span>
            <input
              type="email"
              defaultValue={user?.email}
              disabled
              className="h-11 w-full rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-muted outline-none disabled:cursor-not-allowed"
            />
          </label>
          <div>
            <span className="mb-2 block text-sm font-medium text-content-secondary">Role</span>
            <span className="inline-flex rounded-full bg-brand/10 px-2.5 py-1 text-xs text-brand-400">{user?.role}</span>
          </div>
          <div>
            <span className="mb-2 block text-sm font-medium text-content-secondary">Theme</span>
            <ThemeSwitcher showLabels />
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-surface p-4">
        <div className="mb-3 flex items-center gap-2">
          <Info className="h-4 w-4 text-brand-400" aria-hidden="true" />
          <h3 className="text-sm font-medium text-content-primary">System Information</h3>
        </div>
        <div>
          <InfoRow label="Version" value={APP_VERSION} />
          <InfoRow label="Auth provider" value={provider ?? "—"} />
          <InfoRow label="API base URL" value={API_BASE_URL || "same-origin"} />
          <InfoRow label="Theme" value={theme === "system" ? `System (${resolvedTheme})` : theme} />
          <InfoRow label="Timezone" value={timezone} />
        </div>
      </div>
    </div>
  );
}

function NotificationsTab() {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="divide-y divide-line">
        <Toggle label="Alert notifications" description="Get notified when new alerts start firing" defaultChecked />
        <Toggle label="Deployment updates" description="Get notified on rollout success or failure" defaultChecked />
        <Toggle label="Weekly digest" description="A weekly summary email of cluster health" />
      </div>
    </div>
  );
}

function ClusterTab() {
  const [clusterInfo, setClusterInfo] = useState<ClusterInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchClusterInfo()
      .then((info) => {
        if (!cancelled) setClusterInfo(info);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">Preferences</h3>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-content-secondary">Default namespace</span>
          <input
            type="text"
            defaultValue="default"
            className="h-11 w-full max-w-sm rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
          />
        </label>
      </div>

      <div className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-content-primary">Connected Cluster</h3>
        <div>
          <InfoRow label="Server version" value={clusterInfo?.gitVersion ?? "—"} />
          <InfoRow label="Platform" value={clusterInfo?.platform ?? "—"} />
          <InfoRow label="Nodes" value={clusterInfo ? `${clusterInfo.readyNodeCount}/${clusterInfo.nodeCount} ready` : "—"} />
          <InfoRow label="Namespaces" value={clusterInfo ? String(clusterInfo.namespaceCount) : "—"} />
        </div>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>("general");

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <section className="rounded-lg border border-line bg-surface p-5 shadow-panel">
        <p className="text-sm text-brand-400">Settings</p>
        <h2 className="mt-1 text-xl font-semibold text-content-primary">Preferences</h2>
        <p className="mt-1 text-sm text-content-muted">Profile, appearance, notifications, and cluster defaults.</p>
      </section>

      <div className="flex items-center gap-0.5 self-start rounded-md border border-line bg-surface-hover/60 p-0.5">
        {TABS.map((item) => {
          const Icon = item.icon;
          const isActive = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={clsx(
                "flex h-9 items-center gap-2 rounded px-3 text-sm transition",
                isActive
                  ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                  : "text-content-muted hover:text-content-primary",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </div>

      {tab === "general" ? <GeneralTab /> : null}
      {tab === "notifications" ? <NotificationsTab /> : null}
      {tab === "cluster" ? <ClusterTab /> : null}
    </div>
  );
}
