import { useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Generic helpers
// ---------------------------------------------------------------------------

function randomBetween(min: number, max: number): number {
  return Math.random() * (max - min) + min;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function randomId(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function formatRelativeTime(date: Date, now: Date = new Date()): string {
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}d ago`;
}

/** Mirror of formatRelativeTime for dates in the future — "in 7h", "in 3d". */
export function formatRelativeFuture(date: Date, now: Date = new Date()): string {
  const diffMin = Math.round((date.getTime() - now.getTime()) / 60000);
  if (diffMin <= 0) return "due now";
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `in ${diffHour}h`;
  return `in ${Math.round(diffHour / 24)}d`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function timeLabel(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ---------------------------------------------------------------------------
// Live time-series (used for CPU / memory / network / disk charts)
// ---------------------------------------------------------------------------

export type SeriesPoint = {
  time: string;
  value: number;
};

function nextRandomWalk(previous: number, volatility: number, min: number, max: number): number {
  return clamp(previous + randomBetween(-volatility, volatility), min, max);
}

function seedSeries(length: number, base: number, volatility: number, min: number, max: number): SeriesPoint[] {
  const points: SeriesPoint[] = [];
  let value = base;
  const now = Date.now();
  for (let i = length - 1; i >= 0; i -= 1) {
    value = nextRandomWalk(value, volatility, min, max);
    points.push({ time: timeLabel(new Date(now - i * 2500)), value: Math.round(value * 10) / 10 });
  }
  return points;
}

type UseLiveSeriesOptions = {
  base: number;
  volatility: number;
  min?: number;
  max?: number;
  length?: number;
  intervalMs?: number;
};

/** A random-walking time series that appends a new point on an interval, dropping the oldest. */
export function useLiveSeries({
  base,
  volatility,
  min = 0,
  max = 100,
  length = 24,
  intervalMs = 2500,
}: UseLiveSeriesOptions): SeriesPoint[] {
  const [series, setSeries] = useState<SeriesPoint[]>(() => seedSeries(length, base, volatility, min, max));
  const lastValue = useRef(series[series.length - 1]?.value ?? base);

  useEffect(() => {
    const id = window.setInterval(() => {
      lastValue.current = nextRandomWalk(lastValue.current, volatility, min, max);
      setSeries((current) => {
        const next = [...current, { time: timeLabel(new Date()), value: Math.round(lastValue.current * 10) / 10 }];
        return next.length > length ? next.slice(next.length - length) : next;
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [volatility, min, max, length, intervalMs]);

  return series;
}

/** A single random-walking number, for stat tiles like "active pods" or "open alerts". */
export function useLiveNumber(base: number, volatility: number, intervalMs = 3000, min = 0, max = Infinity): number {
  const [value, setValue] = useState(base);

  useEffect(() => {
    const id = window.setInterval(() => {
      setValue((current) => Math.round(nextRandomWalk(current, volatility, min, max)));
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [volatility, intervalMs, min, max]);

  return value;
}

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

export type LogLevel = "debug" | "info" | "warn" | "error";

export type LogEntry = {
  id: string;
  timestamp: Date;
  level: LogLevel;
  source: string;
  message: string;
};

const LOG_SOURCES = [
  "api-gateway",
  "auth-service",
  "payments-worker",
  "ingest-controller",
  "scheduler",
  "redis",
  "postgres",
];

const LOG_MESSAGES: Record<LogLevel, string[]> = {
  debug: [
    "cache hit for key session:9fa2",
    "connection pool at 12/50",
    "reconciling desired state",
    "heartbeat sent",
  ],
  info: [
    "request completed in 84ms",
    "deployment rollout progressing (3/5 replicas)",
    "scaled replica set to 4 replicas",
    "config reloaded successfully",
    "leader election won",
  ],
  warn: [
    "request latency above 500ms threshold",
    "readiness probe slow to respond",
    "connection pool nearing capacity",
    "retrying upstream request (attempt 2/3)",
  ],
  error: [
    "connection to database refused",
    "pod OOMKilled, restarting",
    "unhandled exception in request handler",
    "failed to pull image: timeout",
  ],
};

const LOG_LEVEL_WEIGHTS: [LogLevel, number][] = [
  ["debug", 0.35],
  ["info", 0.45],
  ["warn", 0.14],
  ["error", 0.06],
];

function pickLogLevel(): LogLevel {
  const roll = Math.random();
  let cumulative = 0;
  for (const [level, weight] of LOG_LEVEL_WEIGHTS) {
    cumulative += weight;
    if (roll <= cumulative) return level;
  }
  return "info";
}

function createLogEntry(timestamp: Date = new Date()): LogEntry {
  const level = pickLogLevel();
  const source = LOG_SOURCES[Math.floor(Math.random() * LOG_SOURCES.length)];
  const messages = LOG_MESSAGES[level];
  const message = messages[Math.floor(Math.random() * messages.length)];
  return { id: randomId(), timestamp, level, source, message };
}

function seedLogs(count: number): LogEntry[] {
  const now = Date.now();
  const entries: LogEntry[] = [];
  for (let i = count - 1; i >= 0; i -= 1) {
    entries.push(createLogEntry(new Date(now - i * 4000)));
  }
  return entries.reverse();
}

/** Newest-first log list that grows with a new entry on an interval, capped at `cap`. */
export function useLiveLogs(seedCount = 40, intervalMs = 3000, cap = 300): LogEntry[] {
  const [logs, setLogs] = useState<LogEntry[]>(() => seedLogs(seedCount));

  useEffect(() => {
    const id = window.setInterval(() => {
      setLogs((current) => {
        const next = [createLogEntry(), ...current];
        return next.length > cap ? next.slice(0, cap) : next;
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs, cap]);

  return logs;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export type NotificationKind = "info" | "success" | "warning" | "error";

export type NotificationItem = {
  id: string;
  title: string;
  description: string;
  kind: NotificationKind;
  createdAt: Date;
  read: boolean;
};

export function generateNotifications(): NotificationItem[] {
  const now = Date.now();
  return [
    {
      id: randomId(),
      title: "Deployment rolled out",
      description: "payments-api v2.4.1 rolled out to 5/5 replicas",
      kind: "success",
      createdAt: new Date(now - 3 * 60 * 1000),
      read: false,
    },
    {
      id: randomId(),
      title: "High memory usage",
      description: "node worker-3 at 91% memory for 10 minutes",
      kind: "warning",
      createdAt: new Date(now - 22 * 60 * 1000),
      read: false,
    },
    {
      id: randomId(),
      title: "Alert firing: PodCrashLooping",
      description: "auth-service-7d9f8 restarted 4 times in 5 minutes",
      kind: "error",
      createdAt: new Date(now - 47 * 60 * 1000),
      read: false,
    },
    {
      id: randomId(),
      title: "Cluster autoscaler scaled up",
      description: "Added 2 nodes to node pool default-pool",
      kind: "info",
      createdAt: new Date(now - 3 * 60 * 60 * 1000),
      read: true,
    },
    {
      id: randomId(),
      title: "Certificate renewed",
      description: "TLS certificate for *.dashboard.internal renewed",
      kind: "success",
      createdAt: new Date(now - 26 * 60 * 60 * 1000),
      read: true,
    },
  ];
}

// ---------------------------------------------------------------------------
// Traces
// ---------------------------------------------------------------------------

export type SpanStatus = "ok" | "error";

export type TraceSpan = {
  id: string;
  name: string;
  service: string;
  startOffsetMs: number;
  durationMs: number;
  status: SpanStatus;
};

export type Trace = {
  id: string;
  rootService: string;
  operation: string;
  durationMs: number;
  status: SpanStatus;
  timestamp: Date;
  spans: TraceSpan[];
};

function buildTrace(id: string, rootService: string, operation: string, minutesAgo: number, hasError: boolean): Trace {
  const spans: TraceSpan[] = [
    { id: randomId(), name: `${operation} (root)`, service: rootService, startOffsetMs: 0, durationMs: 0, status: "ok" },
    { id: randomId(), name: "auth.verify", service: "auth-service", startOffsetMs: 4, durationMs: randomBetween(8, 20), status: "ok" },
    { id: randomId(), name: "db.query", service: "postgres", startOffsetMs: 26, durationMs: randomBetween(15, 120), status: hasError ? "error" : "ok" },
    { id: randomId(), name: "cache.get", service: "redis", startOffsetMs: 30, durationMs: randomBetween(1, 6), status: "ok" },
    { id: randomId(), name: "downstream.call", service: "payments-worker", startOffsetMs: 60, durationMs: randomBetween(30, 90), status: "ok" },
  ];
  const totalDuration = Math.max(...spans.map((s) => s.startOffsetMs + s.durationMs));
  spans[0].durationMs = totalDuration;

  return {
    id,
    rootService,
    operation,
    durationMs: Math.round(totalDuration),
    status: hasError ? "error" : "ok",
    timestamp: new Date(Date.now() - minutesAgo * 60 * 1000),
    spans: spans.map((s) => ({ ...s, durationMs: Math.round(s.durationMs) })),
  };
}

export function generateTraces(): Trace[] {
  return [
    buildTrace(randomId(), "api-gateway", "POST /v1/checkout", 1, false),
    buildTrace(randomId(), "api-gateway", "GET /v1/orders", 3, false),
    buildTrace(randomId(), "payments-worker", "process.payment", 6, true),
    buildTrace(randomId(), "api-gateway", "POST /v1/auth/login", 9, false),
    buildTrace(randomId(), "ingest-controller", "ingest.batch", 14, false),
    buildTrace(randomId(), "api-gateway", "GET /v1/users/me", 18, false),
    buildTrace(randomId(), "scheduler", "reconcile.deployments", 25, true),
    buildTrace(randomId(), "api-gateway", "GET /v1/dashboard/summary", 33, false),
  ];
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertStatus = "firing" | "acknowledged" | "resolved";

export type AlertItem = {
  id: string;
  name: string;
  severity: AlertSeverity;
  status: AlertStatus;
  resource: string;
  message: string;
  startedAt: Date;
};

export function generateAlerts(): AlertItem[] {
  const now = Date.now();
  return [
    {
      id: randomId(),
      name: "PodCrashLooping",
      severity: "critical",
      status: "firing",
      resource: "auth-service-7d9f8",
      message: "Container restarted 4 times in the last 5 minutes",
      startedAt: new Date(now - 12 * 60 * 1000),
    },
    {
      id: randomId(),
      name: "HighMemoryUsage",
      severity: "warning",
      status: "firing",
      resource: "node/worker-3",
      message: "Memory usage above 90% for 10 minutes",
      startedAt: new Date(now - 34 * 60 * 1000),
    },
    {
      id: randomId(),
      name: "DiskPressure",
      severity: "warning",
      status: "acknowledged",
      resource: "node/worker-1",
      message: "Available disk space below 15%",
      startedAt: new Date(now - 2 * 60 * 60 * 1000),
    },
    {
      id: randomId(),
      name: "HighRequestLatency",
      severity: "warning",
      status: "firing",
      resource: "deployment/api-gateway",
      message: "p95 latency above 500ms for 5 minutes",
      startedAt: new Date(now - 8 * 60 * 1000),
    },
    {
      id: randomId(),
      name: "CertificateExpiringSoon",
      severity: "info",
      status: "firing",
      resource: "secret/tls-dashboard",
      message: "Certificate expires in 14 days",
      startedAt: new Date(now - 5 * 60 * 60 * 1000),
    },
    {
      id: randomId(),
      name: "DeploymentRolloutStuck",
      severity: "critical",
      status: "resolved",
      resource: "deployment/payments-worker",
      message: "Rollout did not progress for 15 minutes",
      startedAt: new Date(now - 20 * 60 * 60 * 1000),
    },
  ];
}

// AI assistant (canned replies)
// ---------------------------------------------------------------------------

const CANNED_REPLIES: { match: RegExp; reply: string }[] = [
  {
    match: /pod|crash|restart/i,
    reply:
      "auth-service-7d9f8 has restarted 4 times in the last 5 minutes with an OOMKilled reason. I'd suggest checking its memory limits or recent traffic spikes.",
  },
  {
    match: /cpu|memory|usage/i,
    reply:
      "Cluster-wide CPU is averaging 62% and memory 71% over the last hour. Node worker-3 is the hottest node at 91% memory.",
  },
  {
    match: /alert|firing/i,
    reply:
      "There are 4 alerts currently firing: PodCrashLooping (critical), HighMemoryUsage (warning), HighRequestLatency (warning), and CertificateExpiringSoon (info).",
  },
  {
    match: /log|error/i,
    reply:
      "The most frequent error in the last 15 minutes is \"connection to database refused\" from the payments-worker source.",
  },
];

const DEFAULT_REPLIES = [
  "I'm a stubbed assistant for now — once real cluster data is wired up in a later stage, I'll be able to answer that with live data.",
  "Good question. That capability isn't connected yet, but the plan is to answer questions like this from live metrics, logs, and traces.",
  "I don't have a live backend yet, so consider this a preview of the AI panel — ask me about pods, CPU/memory, alerts, or logs for a canned example.",
];

export function getCannedReply(message: string): string {
  for (const { match, reply } of CANNED_REPLIES) {
    if (match.test(message)) return reply;
  }
  return DEFAULT_REPLIES[Math.floor(Math.random() * DEFAULT_REPLIES.length)];
}

// ---------------------------------------------------------------------------
// Search index
// ---------------------------------------------------------------------------

export type SearchResult = {
  id: string;
  label: string;
  category: string;
  href: string;
};

export const mockSearchIndex: SearchResult[] = [
  { id: randomId(), label: "auth-service-7d9f8", category: "Pod", href: "/logs" },
  { id: randomId(), label: "payments-worker", category: "Deployment", href: "/metrics" },
  { id: randomId(), label: "api-gateway", category: "Service", href: "/traces" },
  { id: randomId(), label: "worker-3", category: "Node", href: "/metrics" },
  { id: randomId(), label: "PodCrashLooping", category: "Alert rule", href: "/alerts" },
  { id: randomId(), label: "default", category: "Namespace", href: "/metrics" },
  { id: randomId(), label: "tls-dashboard", category: "Secret", href: "/settings" },
];
