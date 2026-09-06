import clsx from "clsx";

import type { AlertSeverity, AlertStatus, LogLevel, SpanStatus } from "@/utils/mockData";
import type { EventType } from "@/services/events";
import type { IncidentSeverity, IncidentStatus } from "@/services/incidents";
import type { AuditResult, ClusterStatus, UserRole, UserStatus } from "@/utils/mockAdmin";
import type { ReportStatus } from "@/utils/mockReports";

export type PillTone = "green" | "amber" | "red" | "blue" | "violet" | "neutral";

const PILL_TONES: Record<PillTone, string> = {
  green: "bg-signal-green/10 text-signal-green",
  amber: "bg-signal-amber/10 text-signal-amber",
  red: "bg-signal-red/10 text-signal-red",
  blue: "bg-signal-blue/10 text-signal-blue",
  violet: "bg-brand/10 text-brand-400",
  neutral: "bg-surface-hover text-content-secondary",
};

/** Rounded status pill — the shared base for the typed badges below. */
export function Pill({ label, tone = "neutral", className }: { label: string; tone?: PillTone; className?: string }) {
  return (
    <span className={clsx("inline-block shrink-0 rounded-full px-2 py-0.5 text-xs font-medium", PILL_TONES[tone], className)}>
      {label}
    </span>
  );
}

const LOG_LEVEL_STYLES: Record<LogLevel, string> = {
  debug: "bg-surface-hover text-content-muted",
  info: "bg-signal-blue/10 text-signal-blue",
  warn: "bg-signal-amber/10 text-signal-amber",
  error: "bg-signal-red/10 text-signal-red",
};

export function LevelBadge({ level }: { level: LogLevel }) {
  return (
    <span className={clsx("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide", LOG_LEVEL_STYLES[level])}>
      {level}
    </span>
  );
}

const SEVERITY_STYLES: Record<AlertSeverity, string> = {
  critical: "bg-signal-red/10 text-signal-red",
  warning: "bg-signal-amber/10 text-signal-amber",
  info: "bg-signal-blue/10 text-signal-blue",
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize", SEVERITY_STYLES[severity])}>
      {severity}
    </span>
  );
}

const ALERT_STATUS_STYLES: Record<AlertStatus, string> = {
  firing: "bg-signal-red/10 text-signal-red",
  acknowledged: "bg-signal-amber/10 text-signal-amber",
  resolved: "bg-signal-green/10 text-signal-green",
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return (
    <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize", ALERT_STATUS_STYLES[status])}>
      {status}
    </span>
  );
}

const SPAN_STATUS_STYLES: Record<SpanStatus, string> = {
  ok: "bg-signal-green/10 text-signal-green",
  error: "bg-signal-red/10 text-signal-red",
};

export function SpanStatusBadge({ status }: { status: SpanStatus }) {
  return (
    <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium uppercase", SPAN_STATUS_STYLES[status])}>
      {status}
    </span>
  );
}

const EVENT_TYPE_TONES: Record<EventType, PillTone> = {
  Normal: "neutral",
  Warning: "amber",
};

export function EventTypeBadge({ type }: { type: EventType }) {
  return <Pill label={type} tone={EVENT_TYPE_TONES[type]} />;
}

const INCIDENT_SEVERITY_TONES: Record<IncidentSeverity, PillTone> = {
  sev1: "red",
  sev2: "amber",
  sev3: "blue",
};

const INCIDENT_SEVERITY_LABELS: Record<IncidentSeverity, string> = {
  sev1: "SEV1",
  sev2: "SEV2",
  sev3: "SEV3",
};

export function IncidentSeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return <Pill label={INCIDENT_SEVERITY_LABELS[severity]} tone={INCIDENT_SEVERITY_TONES[severity]} />;
}

const INCIDENT_STATUS_TONES: Record<IncidentStatus, PillTone> = {
  open: "red",
  investigating: "amber",
  mitigated: "blue",
  resolved: "green",
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  return <Pill label={status} tone={INCIDENT_STATUS_TONES[status]} className="capitalize" />;
}

const REPORT_STATUS_TONES: Record<ReportStatus, PillTone> = {
  ready: "green",
  generating: "blue",
  failed: "red",
};

export function ReportStatusBadge({ status }: { status: ReportStatus }) {
  return <Pill label={status} tone={REPORT_STATUS_TONES[status]} className="capitalize" />;
}

const CLUSTER_STATUS_TONES: Record<ClusterStatus, PillTone> = {
  connected: "green",
  degraded: "amber",
  disconnected: "red",
};

export function ClusterStatusBadge({ status }: { status: ClusterStatus }) {
  return <Pill label={status} tone={CLUSTER_STATUS_TONES[status]} className="capitalize" />;
}

const USER_STATUS_TONES: Record<UserStatus, PillTone> = {
  active: "green",
  invited: "blue",
  disabled: "neutral",
};

export function UserStatusBadge({ status }: { status: UserStatus }) {
  return <Pill label={status} tone={USER_STATUS_TONES[status]} className="capitalize" />;
}

const ROLE_TONES: Record<UserRole, PillTone> = {
  admin: "violet",
  operator: "blue",
  developer: "neutral",
  viewer: "neutral",
};

export function RoleBadge({ role }: { role: UserRole }) {
  return <Pill label={role} tone={ROLE_TONES[role]} className="capitalize" />;
}

export function AuditResultBadge({ result }: { result: AuditResult }) {
  return <Pill label={result} tone={result === "success" ? "green" : "red"} className="capitalize" />;
}
