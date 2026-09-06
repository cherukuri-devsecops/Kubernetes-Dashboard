import { apiFetch } from "@/api/client";

export type EventType = "Normal" | "Warning";

/** Wire shape from /api/events — timestamps are ISO strings. */
type ClusterEventResponse = {
  id: string;
  type: EventType;
  reason: string;
  object: string;
  namespace: string | null;
  source: string;
  message: string;
  count: number;
  firstSeen: string | null;
  lastSeen: string | null;
};

export type ClusterEvent = {
  id: string;
  type: EventType;
  reason: string;
  object: string;
  namespace: string;
  source: string;
  message: string;
  count: number;
  firstSeen: Date;
  lastSeen: Date;
};

function toDate(value: string | null, fallback: Date): Date {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed;
}

export async function fetchEvents(namespace: string | null, limit = 300): Promise<ClusterEvent[]> {
  const params = new URLSearchParams();
  if (namespace) params.set("namespace", namespace);
  params.set("limit", String(limit));

  const events = await apiFetch<ClusterEventResponse[]>(`/api/events?${params.toString()}`);
  const now = new Date();

  return events.map((event) => {
    const lastSeen = toDate(event.lastSeen, now);
    return {
      ...event,
      namespace: event.namespace ?? "—",
      lastSeen,
      firstSeen: toDate(event.firstSeen, lastSeen),
    };
  });
}
