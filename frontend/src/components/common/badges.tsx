import clsx from "clsx";

import type { AlertSeverity, AlertState } from "@/services/alerts";
import type { SpanStatus } from "@/services/traces";
import type { LogLevel } from "@/services/logs";
import type { EventType } from "@/services/events";
import type { IncidentSeverity, IncidentStatus } from "@/services/incidents";
import type { RbacRole, SubjectKind } from "@/services/rbac";

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

type RuleState = AlertState | "inactive";

const ALERT_STATE_STYLES: Record<RuleState, string> = {
  firing: "bg-signal-red/10 text-signal-red",
  pending: "bg-signal-amber/10 text-signal-amber",
  inactive: "bg-signal-green/10 text-signal-green",
};

export function AlertStateBadge({ state }: { state: RuleState }) {
  return (
    <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize", ALERT_STATE_STYLES[state])}>
      {state}
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

const SUBJECT_KIND_TONES: Record<string, PillTone> = {
  User: "violet",
  Group: "blue",
  ServiceAccount: "neutral",
};

export function SubjectKindBadge({ kind }: { kind: SubjectKind }) {
  return <Pill label={kind} tone={SUBJECT_KIND_TONES[kind] ?? "neutral"} />;
}

/** Whether a role's verbs can mutate the cluster, not who holds it. */
export function AccessBadge({ access }: { access: RbacRole["access"] }) {
  return <Pill label={access} tone={access === "write" ? "amber" : "green"} className="capitalize" />;
}

export function ScopeBadge({ scope }: { scope: string }) {
  return <Pill label={scope || "—"} tone={scope === "Cluster" ? "violet" : "neutral"} />;
}
