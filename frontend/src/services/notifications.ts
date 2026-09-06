import { fetchAlerts } from "@/services/alerts";
import { fetchEvents } from "@/services/events";

export type NotificationKind = "info" | "success" | "warning" | "error";

export type NotificationItem = {
  id: string;
  title: string;
  description: string;
  kind: NotificationKind;
  createdAt: Date;
  href: string;
};

const MAX_ITEMS = 12;

/** The notification feed is a view over things that actually happened in the
 * cluster: alerts Prometheus is raising, and Warning events from the API. */
export async function fetchNotifications(): Promise<NotificationItem[]> {
  const [alertsResult, eventsResult] = await Promise.allSettled([fetchAlerts(), fetchEvents(null, 100)]);

  const items: NotificationItem[] = [];

  if (alertsResult.status === "fulfilled") {
    for (const alert of alertsResult.value.alerts) {
      items.push({
        id: `alert:${alert.id}`,
        title: `${alert.state === "pending" ? "Pending" : "Firing"}: ${alert.name}`,
        description: alert.message || `${alert.resource} — ${alert.severity}`,
        kind: alert.severity === "critical" ? "error" : alert.severity === "warning" ? "warning" : "info",
        createdAt: alert.startedAt,
        href: "/alerts",
      });
    }
  }

  if (eventsResult.status === "fulfilled") {
    for (const event of eventsResult.value) {
      if (event.type !== "Warning") continue;
      items.push({
        id: `event:${event.id}`,
        title: `${event.reason} — ${event.object}`,
        description: `${event.namespace}: ${event.message}`,
        kind: "warning",
        createdAt: event.lastSeen,
        href: "/events",
      });
    }
  }

  items.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
  return items.slice(0, MAX_ITEMS);
}
