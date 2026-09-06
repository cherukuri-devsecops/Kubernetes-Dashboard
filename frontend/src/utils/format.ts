/** Shared display formatting. Values come from the cluster; this only renders them. */

export function formatRelativeTime(date: Date, now: Date = new Date()): string {
  const diffSec = Math.round((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  return `${Math.round(diffHour / 24)}d ago`;
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

const BYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const exponent = Math.min(Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)), BYTE_UNITS.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 100 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${BYTE_UNITS[exponent]}`;
}

/** Parses an ISO timestamp, falling back when the API sends null or junk. */
export function parseDate(value: string | null | undefined, fallback: Date = new Date()): Date {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed;
}
