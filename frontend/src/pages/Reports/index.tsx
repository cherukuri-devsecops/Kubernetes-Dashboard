import { useEffect, useMemo, useState } from "react";
import { Activity, Boxes, Download, FileBarChart, FileText, LifeBuoy, RefreshCw, ShieldCheck, type LucideIcon } from "lucide-react";
import clsx from "clsx";

import { DataTable, type Column } from "@/components/tables/DataTable";
import { Pill } from "@/components/common/badges";
import {
  downloadReport,
  fetchReportTemplates,
  generateReport,
  type GeneratedReport,
  type ReportFormat,
  type ReportTemplate,
} from "@/services/reports";
import { formatRelativeTime, parseDate } from "@/utils/format";

type ReportRow = Record<string, string | number>;

const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  "cluster-health": Boxes,
  "resource-utilization": Activity,
  "workload-inventory": FileBarChart,
  "pod-restarts": LifeBuoy,
  "rbac-audit": ShieldCheck,
};

const FORMATS: ReportFormat[] = ["csv", "json"];

export function ReportsPage() {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState<ReportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReportTemplates()
      .then((list) => {
        setTemplates(list);
        setSelectedId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : "Could not load report templates"));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;

    setGenerating(true);
    setReport(null);
    generateReport(selectedId)
      .then((result) => {
        if (cancelled) return;
        setReport(result);
        setError(null);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Could not build the report");
      })
      .finally(() => {
        if (!cancelled) setGenerating(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const columns: Column<ReportRow>[] = useMemo(
    () =>
      (report?.columns ?? []).map((column, index) => ({
        key: column.key,
        header: column.label,
        cellClassName: index === 0 ? "text-content-primary" : undefined,
        render: (row: ReportRow) => {
          const value = row[column.key];
          return value === "" || value === undefined ? "—" : String(value);
        },
      })),
    [report],
  );

  async function handleDownload(format: ReportFormat) {
    if (!selectedId) return;
    setDownloading(format);
    try {
      await downloadReport(selectedId, format);
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  }

  function regenerate() {
    // Re-running the same selection re-queries the cluster for a fresh snapshot.
    const current = selectedId;
    setSelectedId(null);
    window.setTimeout(() => setSelectedId(current), 0);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div>
        <p className="text-sm text-brand-400">Reports</p>
        <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Cluster reports</h2>
        <p className="mt-0.5 text-xs text-content-muted">
          Each report is computed when you open it, from the Kubernetes API and Prometheus. Nothing is cached.
        </p>
      </div>

      {error ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{error}</p>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {templates.map((template) => {
          const Icon = TEMPLATE_ICONS[template.id] ?? FileText;
          const active = template.id === selectedId;
          return (
            <button
              key={template.id}
              type="button"
              onClick={() => setSelectedId(template.id)}
              className={clsx(
                "flex flex-col gap-2 rounded-lg border p-4 text-left transition",
                active
                  ? "border-brand/40 bg-brand/[0.08] ring-1 ring-brand/30"
                  : "border-line bg-surface hover:bg-surface-hover",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <Icon className={clsx("h-5 w-5", active ? "text-brand-400" : "text-content-muted")} aria-hidden="true" />
                <Pill label={template.category} />
              </div>
              <p className="text-sm font-medium text-content-primary">{template.name}</p>
              <p className="text-[11px] leading-4 text-content-muted">{template.description}</p>
            </button>
          );
        })}
      </section>

      {report ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3">
            <div>
              <p className="text-sm font-medium text-content-primary">{report.name}</p>
              <p className="text-xs text-content-muted">
                {report.rowCount} row{report.rowCount === 1 ? "" : "s"} · built{" "}
                {formatRelativeTime(parseDate(report.generatedAt))} · source: {report.source}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={regenerate}
                disabled={generating}
                className="flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary disabled:opacity-60"
              >
                <RefreshCw className={clsx("h-3.5 w-3.5", generating && "animate-spin")} aria-hidden="true" />
                Refresh
              </button>
              {FORMATS.map((format) => (
                <button
                  key={format}
                  type="button"
                  onClick={() => handleDownload(format)}
                  disabled={downloading !== null}
                  className="flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  {downloading === format ? "Preparing…" : format.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
            {report.summary.map((item) => (
              <article key={item.label} className="rounded-lg border border-line bg-surface p-3">
                <p className="text-xs text-content-muted">{item.label}</p>
                <p className="mt-1 text-sm font-semibold text-content-primary">{item.value}</p>
              </article>
            ))}
          </section>

          <DataTable
            columns={columns}
            rows={report.rows}
            rowKey={(row) => columns.map((column) => String(row[column.key] ?? "")).join("|")}
            emptyMessage="This report returned no rows — nothing in the cluster matched."
            minWidth={960}
          />
        </>
      ) : (
        <p className="rounded-lg border border-line bg-surface px-4 py-8 text-center text-sm text-content-muted">
          {generating ? "Querying the cluster…" : "Select a report to build it from live cluster data."}
        </p>
      )}
    </div>
  );
}
