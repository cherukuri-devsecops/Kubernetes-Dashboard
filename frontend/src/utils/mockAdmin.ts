import { Bell, Cloud, KeyRound, Mail, MessageSquare, Webhook, type LucideIcon } from "lucide-react";

// Stand-in administration data. Mirrors the Data Stores (users / RBAC / clusters /
// audit logs) and Security boxes of the architecture diagram.

export type UserRole = "admin" | "operator" | "developer" | "viewer";
export type AuthProvider = "local" | "google" | "oidc";
export type UserStatus = "active" | "invited" | "disabled";

export type AdminUser = {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  provider: AuthProvider;
  status: UserStatus;
  namespaces: string[];
  lastLogin: Date | null;
};

export type PermissionLevel = "none" | "read" | "write" | "admin";

export type RoleDefinition = {
  key: UserRole;
  label: string;
  description: string;
  permissions: Record<string, PermissionLevel>;
};

export type ClusterStatus = "connected" | "degraded" | "disconnected";

export type RegisteredCluster = {
  id: string;
  name: string;
  endpoint: string;
  version: string;
  environment: string;
  status: ClusterStatus;
  nodes: number;
  lastSync: Date;
};

export type ServiceAccountToken = {
  id: string;
  name: string;
  namespace: string;
  scopes: string[];
  createdAt: Date;
  lastUsed: Date | null;
  expiresAt: Date | null;
};

export type Integration = {
  id: string;
  name: string;
  category: string;
  description: string;
  icon: LucideIcon;
  target: string;
  connected: boolean;
};

export type AuditResult = "success" | "denied";

export type AuditEntry = {
  id: string;
  at: Date;
  actor: string;
  action: string;
  target: string;
  ip: string;
  result: AuditResult;
};

export const PERMISSION_RESOURCES = [
  "Clusters & workloads",
  "Metrics & logs",
  "Alerts & incidents",
  "Reports",
  "Users & RBAC",
  "Settings",
];

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60 * 1000);
const daysAgo = (days: number) => new Date(Date.now() - days * 24 * 60 * 60 * 1000);
const daysAhead = (days: number) => new Date(Date.now() + days * 24 * 60 * 60 * 1000);

export function generateUsers(): AdminUser[] {
  return [
    {
      id: "usr-01",
      name: "Priya Nair",
      email: "priya.nair@example.com",
      role: "admin",
      provider: "google",
      status: "active",
      namespaces: ["*"],
      lastLogin: minutesAgo(14),
    },
    {
      id: "usr-02",
      name: "Marco Bianchi",
      email: "marco.bianchi@example.com",
      role: "operator",
      provider: "oidc",
      status: "active",
      namespaces: ["default", "payments", "platform"],
      lastLogin: minutesAgo(96),
    },
    {
      id: "usr-03",
      name: "Dana Kim",
      email: "dana.kim@example.com",
      role: "operator",
      provider: "google",
      status: "active",
      namespaces: ["platform", "observability"],
      lastLogin: minutesAgo(320),
    },
    {
      id: "usr-04",
      name: "Sam Okafor",
      email: "sam.okafor@example.com",
      role: "developer",
      provider: "local",
      status: "active",
      namespaces: ["payments"],
      lastLogin: daysAgo(2),
    },
    {
      id: "usr-05",
      name: "Lena Fischer",
      email: "lena.fischer@example.com",
      role: "viewer",
      provider: "oidc",
      status: "invited",
      namespaces: ["default"],
      lastLogin: null,
    },
    {
      id: "usr-06",
      name: "Tom Reyes",
      email: "tom.reyes@example.com",
      role: "developer",
      provider: "local",
      status: "disabled",
      namespaces: ["default"],
      lastLogin: daysAgo(64),
    },
  ];
}

export const roleDefinitions: RoleDefinition[] = [
  {
    key: "admin",
    label: "Administrator",
    description: "Full control, including user management, cluster registration, and settings.",
    permissions: {
      "Clusters & workloads": "admin",
      "Metrics & logs": "admin",
      "Alerts & incidents": "admin",
      Reports: "admin",
      "Users & RBAC": "admin",
      Settings: "admin",
    },
  },
  {
    key: "operator",
    label: "Operator",
    description: "Runs the cluster day to day — can act on workloads, alerts, and incidents.",
    permissions: {
      "Clusters & workloads": "write",
      "Metrics & logs": "read",
      "Alerts & incidents": "write",
      Reports: "write",
      "Users & RBAC": "read",
      Settings: "read",
    },
  },
  {
    key: "developer",
    label: "Developer",
    description: "Scoped to their own namespaces, with read access to observability data.",
    permissions: {
      "Clusters & workloads": "read",
      "Metrics & logs": "read",
      "Alerts & incidents": "read",
      Reports: "read",
      "Users & RBAC": "none",
      Settings: "none",
    },
  },
  {
    key: "viewer",
    label: "Viewer",
    description: "Read-only access to dashboards and reports.",
    permissions: {
      "Clusters & workloads": "read",
      "Metrics & logs": "read",
      "Alerts & incidents": "read",
      Reports: "read",
      "Users & RBAC": "none",
      Settings: "none",
    },
  },
];

export function generateClusters(): RegisteredCluster[] {
  return [
    {
      id: "cls-prod-us",
      name: "prod-us-east",
      endpoint: "https://k8s-prod-us-east.example.com",
      version: "v1.30.4",
      environment: "production",
      status: "connected",
      nodes: 12,
      lastSync: minutesAgo(1),
    },
    {
      id: "cls-prod-eu",
      name: "prod-eu-west",
      endpoint: "https://k8s-prod-eu-west.example.com",
      version: "v1.30.4",
      environment: "production",
      status: "degraded",
      nodes: 9,
      lastSync: minutesAgo(4),
    },
    {
      id: "cls-staging",
      name: "staging",
      endpoint: "https://k8s-staging.example.com",
      version: "v1.31.1",
      environment: "staging",
      status: "connected",
      nodes: 5,
      lastSync: minutesAgo(2),
    },
    {
      id: "cls-dev",
      name: "dev-local",
      endpoint: "https://127.0.0.1:6443",
      version: "v1.31.1",
      environment: "development",
      status: "disconnected",
      nodes: 1,
      lastSync: minutesAgo(184),
    },
  ];
}

export function generateServiceAccounts(): ServiceAccountToken[] {
  return [
    {
      id: "sa-01",
      name: "dashboard-backend",
      namespace: "observability",
      scopes: ["read:pods", "read:nodes", "read:events", "read:metrics"],
      createdAt: daysAgo(94),
      lastUsed: minutesAgo(1),
      expiresAt: daysAhead(271),
    },
    {
      id: "sa-02",
      name: "ci-deployer",
      namespace: "platform",
      scopes: ["write:deployments", "read:pods"],
      createdAt: daysAgo(180),
      lastUsed: minutesAgo(45),
      expiresAt: daysAhead(14),
    },
    {
      id: "sa-03",
      name: "report-exporter",
      namespace: "observability",
      scopes: ["read:metrics", "write:reports"],
      createdAt: daysAgo(31),
      lastUsed: minutesAgo(360),
      expiresAt: null,
    },
    {
      id: "sa-04",
      name: "legacy-scraper",
      namespace: "default",
      scopes: ["read:pods"],
      createdAt: daysAgo(402),
      lastUsed: null,
      expiresAt: daysAhead(-3),
    },
  ];
}

export function generateIntegrations(): Integration[] {
  return [
    {
      id: "int-slack",
      name: "Slack",
      category: "Notifications",
      description: "Route firing alerts and incident updates into a channel.",
      icon: MessageSquare,
      target: "#platform-alerts",
      connected: true,
    },
    {
      id: "int-pagerduty",
      name: "PagerDuty",
      category: "On-call",
      description: "Page the on-call rotation for sev1 and sev2 incidents.",
      icon: Bell,
      target: "Platform Escalation Policy",
      connected: true,
    },
    {
      id: "int-email",
      name: "Email (SMTP)",
      category: "Notifications",
      description: "Send alert digests and scheduled reports over SMTP.",
      icon: Mail,
      target: "smtp.example.com:587",
      connected: true,
    },
    {
      id: "int-webhook",
      name: "Webhook",
      category: "Notifications",
      description: "POST alert payloads to an arbitrary HTTPS endpoint.",
      icon: Webhook,
      target: "https://hooks.example.com/k8sobserve",
      connected: false,
    },
    {
      id: "int-s3",
      name: "AWS S3",
      category: "Storage",
      description: "Long-term backup of logs, traces, and generated reports.",
      icon: Cloud,
      target: "s3://k8sobserve-archive",
      connected: true,
    },
    {
      id: "int-secrets",
      name: "AWS Secrets Manager",
      category: "Security",
      description: "Source dashboard credentials through the External Secrets Operator.",
      icon: KeyRound,
      target: "k8sobserve/prod/*",
      connected: false,
    },
  ];
}

export function generateAuditLog(): AuditEntry[] {
  return [
    { id: "aud-01", at: minutesAgo(3), actor: "priya.nair@example.com", action: "incident.acknowledge", target: "INC-1042", ip: "10.42.0.18", result: "success" },
    { id: "aud-02", at: minutesAgo(11), actor: "marco.bianchi@example.com", action: "deployment.scale", target: "payments/payments-worker → 8", ip: "10.42.0.31", result: "success" },
    { id: "aud-03", at: minutesAgo(26), actor: "sam.okafor@example.com", action: "secret.read", target: "kube-system/tls-dashboard", ip: "10.42.2.7", result: "denied" },
    { id: "aud-04", at: minutesAgo(58), actor: "scheduler", action: "report.generate", target: "cluster-health (weekly)", ip: "10.42.0.4", result: "success" },
    { id: "aud-05", at: minutesAgo(92), actor: "priya.nair@example.com", action: "user.invite", target: "lena.fischer@example.com (viewer)", ip: "10.42.0.18", result: "success" },
    { id: "aud-06", at: minutesAgo(140), actor: "dana.kim@example.com", action: "alert.silence", target: "DiskPressure (2h)", ip: "10.42.1.22", result: "success" },
    { id: "aud-07", at: minutesAgo(214), actor: "ci-deployer", action: "deployment.apply", target: "platform/ingest-controller", ip: "10.42.3.9", result: "success" },
    { id: "aud-08", at: minutesAgo(305), actor: "tom.reyes@example.com", action: "auth.login", target: "local provider", ip: "203.0.113.44", result: "denied" },
    { id: "aud-09", at: minutesAgo(430), actor: "priya.nair@example.com", action: "cluster.register", target: "staging", ip: "10.42.0.18", result: "success" },
    { id: "aud-10", at: minutesAgo(602), actor: "marco.bianchi@example.com", action: "rbac.update", target: "role/operator → payments", ip: "10.42.0.31", result: "success" },
  ];
}
