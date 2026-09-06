import { API_BASE_URL, apiFetch } from "@/api/client";
import { AUTH_TOKEN_KEY } from "@/services/auth";

export type ReportFormat = "csv" | "json";

export type ReportTemplate = {
  id: string;
  name: string;
  description: string;
  category: string;
  source: string;
};

export type ReportColumn = {
  key: string;
  label: string;
};

export type ReportSummaryItem = {
  label: string;
  value: string | number;
};

export type GeneratedReport = {
  id: string;
  name: string;
  description: string;
  category: string;
  source: string;
  generatedAt: string;
  rowCount: number;
  columns: ReportColumn[];
  rows: Record<string, string | number>[];
  summary: ReportSummaryItem[];
};

export const fetchReportTemplates = () => apiFetch<ReportTemplate[]>("/api/reports/templates");

export const generateReport = (reportId: string) =>
  apiFetch<GeneratedReport>(`/api/reports/${encodeURIComponent(reportId)}`);

/** Downloads the report the backend builds from live cluster data. Fetched
 * rather than linked so the bearer token can be attached. */
export async function downloadReport(reportId: string, format: ReportFormat): Promise<void> {
  const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
  const response = await fetch(
    `${API_BASE_URL}/api/reports/${encodeURIComponent(reportId)}/download?format=${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) {
    throw new Error(`Report download failed (${response.status})`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${reportId}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
