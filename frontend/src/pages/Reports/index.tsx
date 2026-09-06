import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { CalendarClock, CircleCheck, Download, FileText, Plus, TriangleAlert } from "lucide-react";
import clsx from "clsx";

import { StatTile } from "@/components/cards/StatTile";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { SegmentedTabs } from "@/components/common/SegmentedTabs";
import { Pill, ReportStatusBadge } from "@/components/common/badges";
import { Field, Modal, modalInputClass } from "@/components/modals/Modal";
import { formatRelativeFuture, formatRelativeTime } from "@/utils/mockData";
import {
  formatSize,
  generateReports,
  generateSchedules,
  reportTemplateById,
  reportTemplates,
  type GeneratedReport,
  type ReportFormat,
  type ReportSchedule,
} from "@/utils/mockReports";

type ViewTab = "generated" | "scheduled" | "templates";

const TABS: { key: ViewTab; label: string }[] = [
  { key: "generated", label: "Generated" },
  { key: "scheduled", label: "Scheduled" },
  { key: "templates", label: "Templates" },
];

const PERIODS = ["Last 24 hours", "Last 7 days", "Last 30 days", "Last quarter"];
const FORMATS: ReportFormat[] = ["PDF", "CSV", "JSON"];

function templateName(templateId: string): string {
  return reportTemplateById.get(templateId)?.name ?? templateId;
}

export function ReportsPage() {
  const [tab, setTab] = useState<ViewTab>("generated");
  const [reports, setReports] = useState<GeneratedReport[]>(() => generateReports());
  const [schedules, setSchedules] = useState<ReportSchedule[]>(() => generateSchedules());
  const [modalTemplateId, setModalTemplateId] = useState<string | null>(null);
  const timeouts = useRef<number[]>([]);

  useEffect(() => () => timeouts.current.forEach((id) => window.clearTimeout(id)), []);

  const counts = useMemo(
    () => ({
      ready: reports.filter((report) => report.status === "ready").length,
      generating: reports.filter((report) => report.status === "generating").length,
      failed: reports.filter((report) => report.status === "failed").length,
      schedules: schedules.filter((schedule) => schedule.enabled).length,
    }),
    [reports, schedules],
  );

  function createReport(templateId: string, period: string, format: ReportFormat) {
    const id = `rpt-${Date.now()}`;
    const report: GeneratedReport = {
      id,
      name: `${templateName(templateId)} — ${period}`,
      templateId,
      period,
      format,
      sizeKb: 0,
      status: "generating",
      generatedAt: new Date(),
      requestedBy: "You",
    };
    setReports((current) => [report, ...current]);
    setTab("generated");

    // Stand-in for the backend's async report job finishing.
    const timeoutId = window.setTimeout(() => {
      setReports((current) =>
        current.map((item) =>
          item.id === id ? { ...item, status: "ready", sizeKb: Math.round(200 + Math.random() * 1800) } : item,
        ),
      );
    }, 1800);
    timeouts.current.push(timeoutId);
  }

  function toggleSchedule(id: string) {
    setSchedules((current) =>
      current.map((schedule) => (schedule.id === id ? { ...schedule, enabled: !schedule.enabled } : schedule)),
    );
  }

  const reportColumns: Column<GeneratedReport>[] = [
    { key: "name", header: "Report", cellClassName: "text-content-primary", render: (report) => report.name },
    { key: "template", header: "Type", render: (report) => templateName(report.templateId) },
    { key: "period", header: "Period", render: (report) => report.period },
    { key: "format", header: "Format", render: (report) => <Pill label={report.format} tone="neutral" /> },
    { key: "size", header: "Size", render: (report) => formatSize(report.sizeKb) },
    { key: "requestedBy", header: "Requested by", render: (report) => report.requestedBy },
    { key: "generatedAt", header: "Generated", render: (report) => formatRelativeTime(report.generatedAt) },
    { key: "status", header: "Status", render: (report) => <ReportStatusBadge status={report.status} /> },
    {
      key: "actions",
      header: "",
      render: (report) => (
        <button
          type="button"
          disabled={report.status !== "ready"}
          title={report.status === "ready" ? "Download report" : "Report is not ready"}
          className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          Download
        </button>
      ),
    },
  ];

  const scheduleColumns: Column<ReportSchedule>[] = [
    { key: "name", header: "Schedule", cellClassName: "text-content-primary", render: (schedule) => schedule.name },
    { key: "template", header: "Report", render: (schedule) => templateName(schedule.templateId) },
    { key: "cadence", header: "Cadence", render: (schedule) => <Pill label={schedule.cadence} tone="violet" className="capitalize" /> },
    { key: "nextRun", header: "Next run", render: (schedule) => (schedule.enabled ? formatRelativeFuture(schedule.nextRun) : "paused") },
    { key: "recipients", header: "Recipients", render: (schedule) => schedule.recipients.join(", ") },
    { key: "format", header: "Format", render: (schedule) => schedule.format },
    {
      key: "enabled",
      header: "Enabled",
      render: (schedule) => <Switch checked={schedule.enabled} onChange={() => toggleSchedule(schedule.id)} label={schedule.name} />,
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Reports</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Reports & exports</h2>
        </div>
        <button
          type="button"
          onClick={() => setModalTemplateId(reportTemplates[0].id)}
          className="flex h-8 items-center gap-1.5 rounded-md bg-brand px-3 text-xs font-medium text-white transition hover:bg-brand-600"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          Generate report
        </button>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Reports Ready" value={counts.ready} icon={CircleCheck} tone="green" />
        <StatTile label="Generating" value={counts.generating} icon={FileText} tone="blue" />
        <StatTile label="Failed" value={counts.failed} icon={TriangleAlert} tone={counts.failed > 0 ? "red" : "neutral"} />
        <StatTile label="Active Schedules" value={counts.schedules} icon={CalendarClock} tone="neutral" />
      </section>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3">
        <SegmentedTabs options={TABS} value={tab} onChange={setTab} />
        <span className="text-xs text-content-muted">
          {tab === "generated"
            ? `${reports.length} reports in the last 30 days`
            : tab === "scheduled"
              ? `${schedules.length} schedules`
              : `${reportTemplates.length} templates`}
        </span>
      </div>

      {tab === "generated" ? (
        <DataTable
          columns={reportColumns}
          rows={reports}
          rowKey={(report) => report.id}
          emptyMessage="No reports generated yet."
          minWidth={1100}
        />
      ) : null}

      {tab === "scheduled" ? (
        <DataTable
          columns={scheduleColumns}
          rows={schedules}
          rowKey={(schedule) => schedule.id}
          emptyMessage="No schedules configured."
          minWidth={1000}
        />
      ) : null}

      {tab === "templates" ? (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {reportTemplates.map((template) => {
            const Icon = template.icon;
            return (
              <article key={template.id} className="flex flex-col rounded-lg border border-line bg-surface p-4">
                <div className="mb-3 flex items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-md bg-brand/10 text-brand-400">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-content-primary">{template.name}</h3>
                    <p className="text-xs text-content-muted">{template.category}</p>
                  </div>
                </div>
                <p className="text-xs leading-5 text-content-secondary">{template.description}</p>
                <ul className="mt-3 flex flex-wrap gap-1.5">
                  {template.sections.map((section) => (
                    <li key={section} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-content-muted">
                      {section}
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => setModalTemplateId(template.id)}
                  className="mt-4 flex h-8 w-full items-center justify-center gap-1.5 rounded-md border border-line text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  Generate
                </button>
              </article>
            );
          })}
        </section>
      ) : null}

      <GenerateReportModal
        templateId={modalTemplateId}
        onClose={() => setModalTemplateId(null)}
        onSubmit={(templateId, period, format) => {
          createReport(templateId, period, format);
          setModalTemplateId(null);
        }}
      />
    </div>
  );
}

type GenerateReportModalProps = {
  templateId: string | null;
  onClose: () => void;
  onSubmit: (templateId: string, period: string, format: ReportFormat) => void;
};

function GenerateReportModal({ templateId, onClose, onSubmit }: GenerateReportModalProps) {
  const [selectedTemplate, setSelectedTemplate] = useState(templateId ?? reportTemplates[0].id);
  const [period, setPeriod] = useState(PERIODS[1]);
  const [format, setFormat] = useState<ReportFormat>("PDF");
  const [recipients, setRecipients] = useState("");

  useEffect(() => {
    if (!templateId) return;
    setSelectedTemplate(templateId);
    setFormat(reportTemplateById.get(templateId)?.defaultFormat ?? "PDF");
  }, [templateId]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(selectedTemplate, period, format);
  }

  return (
    <Modal
      open={templateId !== null}
      title="Generate report"
      description="Runs once against the selected period. Scheduled delivery is configured on the Scheduled tab."
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="h-8 rounded-md border border-line px-3 text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="generate-report-form"
            className="h-8 rounded-md bg-brand px-3 text-xs font-medium text-white transition hover:bg-brand-600"
          >
            Generate
          </button>
        </>
      }
    >
      <form id="generate-report-form" onSubmit={handleSubmit} className="space-y-3">
        <Field label="Report template">
          <select value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value)} className={modalInputClass}>
            {reportTemplates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Period">
          <select value={period} onChange={(event) => setPeriod(event.target.value)} className={modalInputClass}>
            {PERIODS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Format">
          <select value={format} onChange={(event) => setFormat(event.target.value as ReportFormat)} className={modalInputClass}>
            {FORMATS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Email to (optional)" hint="Comma-separated addresses. Leave empty to keep the report in the dashboard.">
          <input
            type="text"
            value={recipients}
            onChange={(event) => setRecipients(event.target.value)}
            placeholder="platform-team@example.com"
            className={modalInputClass}
          />
        </Field>
      </form>
    </Modal>
  );
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={`Enable ${label}`}
      onClick={onChange}
      className={clsx(
        "relative h-5 w-9 shrink-0 rounded-full transition",
        checked ? "bg-brand" : "bg-surface-hover ring-1 ring-inset ring-line",
      )}
    >
      <span
        className={clsx(
          "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all",
          checked ? "left-[1.125rem]" : "left-0.5",
        )}
      />
    </button>
  );
}
