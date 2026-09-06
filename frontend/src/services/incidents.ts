import { apiFetch } from "@/api/client";

export type IncidentSeverity = "sev1" | "sev2" | "sev3";
export type IncidentStatus = "open" | "investigating" | "mitigated" | "resolved";

type IncidentUpdateResponse = {
  id: string;
  at: string | null;
  actor: string;
  text: string;
};

type IncidentResponse = {
  id: string;
  title: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  service: string;
  namespace: string;
  assignee: string;
  openedAt: string | null;
  resolvedAt: string | null;
  summary: string;
  rootCause: string | null;
  linkedAlerts: string[];
  timeline: IncidentUpdateResponse[];
};

export type IncidentUpdate = {
  id: string;
  at: Date;
  actor: string;
  text: string;
};

export type Incident = Omit<IncidentResponse, "openedAt" | "resolvedAt" | "timeline"> & {
  openedAt: Date;
  resolvedAt: Date | null;
  timeline: IncidentUpdate[];
};

function toDate(value: string | null, fallback: Date): Date {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed;
}

function toIncident(incident: IncidentResponse): Incident {
  const openedAt = toDate(incident.openedAt, new Date());
  return {
    ...incident,
    openedAt,
    resolvedAt: incident.resolvedAt ? toDate(incident.resolvedAt, openedAt) : null,
    timeline: incident.timeline.map((update) => ({ ...update, at: toDate(update.at, openedAt) })),
  };
}

export async function fetchIncidents(): Promise<Incident[]> {
  const incidents = await apiFetch<IncidentResponse[]>("/api/incidents");
  return incidents.map(toIncident);
}

export async function updateIncidentStatus(
  incidentId: string,
  status: IncidentStatus,
  note?: string,
): Promise<Incident> {
  const incident = await apiFetch<IncidentResponse>(`/api/incidents/${encodeURIComponent(incidentId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, note }),
  });
  return toIncident(incident);
}

export async function addIncidentUpdate(incidentId: string, text: string): Promise<Incident> {
  const incident = await apiFetch<IncidentResponse>(`/api/incidents/${encodeURIComponent(incidentId)}/updates`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  return toIncident(incident);
}

/** Mean time to resolve, in minutes, across incidents that have a resolution time. */
export function meanTimeToResolveMinutes(incidents: Incident[]): number | null {
  const resolved = incidents.filter((incident): incident is Incident & { resolvedAt: Date } => incident.resolvedAt !== null);
  if (resolved.length === 0) return null;
  const total = resolved.reduce(
    (sum, incident) => sum + (incident.resolvedAt.getTime() - incident.openedAt.getTime()) / 60000,
    0,
  );
  return Math.round(total / resolved.length);
}
