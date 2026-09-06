import {
  Activity,
  Boxes,
  DollarSign,
  FileBarChart,
  LifeBuoy,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

// Stand-in report catalog for the Reports UI. Swap for the /api/reports endpoints
// once the backend reports service exists.

export type ReportFormat = "PDF" | "CSV" | "JSON";
export type ReportStatus = "ready" | "generating" | "failed";
export type ReportCadence = "daily" | "weekly" | "monthly" | "quarterly";

export type ReportTemplate = {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: LucideIcon;
  defaultFormat: ReportFormat;
  sections: string[];
};

export type GeneratedReport = {
  id: string;
  name: string;
  templateId: string;
  period: string;
  format: ReportFormat;
  sizeKb: number;
  status: ReportStatus;
  generatedAt: Date;
  requestedBy: string;
};

export type ReportSchedule = {
  id: string;
  name: string;
  templateId: string;
  cadence: ReportCadence;
  nextRun: Date;
  recipients: string[];
  format: ReportFormat;
  enabled: boolean;
};

export const reportTemplates: ReportTemplate[] = [
  {
    id: "cluster-health",
    name: "Cluster Health Summary",
    description: "Node readiness, pod restarts, control-plane availability, and capacity headroom.",
    category: "Operations",
    icon: Boxes,
    defaultFormat: "PDF",
    sections: ["Node status", "Pod health", "Restart hotspots", "Capacity headroom"],
  },
  {
    id: "resource-utilization",
    name: "Resource Utilization",
    description: "CPU, memory, storage, and network usage per namespace and workload.",
    category: "Capacity",
    icon: Activity,
    defaultFormat: "CSV",
    sections: ["CPU by namespace", "Memory by namespace", "Storage growth", "Top workloads"],
  },
  {
    id: "cost-allocation",
    name: "Cost Allocation",
    description: "Requested vs. used resources translated into per-team spend.",
    category: "FinOps",
    icon: DollarSign,
    defaultFormat: "CSV",
    sections: ["Spend by team", "Idle capacity", "Over-provisioned workloads"],
  },
  {
    id: "incident-postmortem",
    name: "Incident Postmortem",
    description: "Timeline, impact, root cause, and follow-up actions for a selected incident.",
    category: "Reliability",
    icon: LifeBuoy,
    defaultFormat: "PDF",
    sections: ["Impact summary", "Timeline", "Root cause", "Action items"],
  },
  {
    id: "sla-uptime",
    name: "SLA / Uptime",
    description: "Service availability against target SLOs, with error budget burn-down.",
    category: "Reliability",
    icon: FileBarChart,
    defaultFormat: "PDF",
    sections: ["Availability by service", "Error budget", "Longest outages"],
  },
  {
    id: "security-audit",
    name: "Security & RBAC Audit",
    description: "Role bindings, service accounts, privileged workloads, and audit-log anomalies.",
    category: "Security",
    icon: ShieldCheck,
    defaultFormat: "PDF",
    sections: ["Role bindings", "Service accounts", "Privileged pods", "Audit anomalies"],
  },
];

export const reportTemplateById = new Map(reportTemplates.map((template) => [template.id, template]));

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000);
const hoursAhead = (hours: number) => new Date(Date.now() + hours * 60 * 60 * 1000);

export function generateReports(): GeneratedReport[] {
  return [
    {
      id: "rpt-2291",
      name: "Cluster Health Summary — Aug 25–Sep 1",
      templateId: "cluster-health",
      period: "Last 7 days",
      format: "PDF",
      sizeKb: 842,
      status: "ready",
      generatedAt: hoursAgo(6),
      requestedBy: "scheduler",
    },
    {
      id: "rpt-2290",
      name: "Resource Utilization — August",
      templateId: "resource-utilization",
      period: "Last 30 days",
      format: "CSV",
      sizeKb: 2140,
      status: "ready",
      generatedAt: hoursAgo(29),
      requestedBy: "Priya N.",
    },
    {
      id: "rpt-2289",
      name: "Incident Postmortem — INC-1039",
      templateId: "incident-postmortem",
      period: "Incident window",
      format: "PDF",
      sizeKb: 356,
      status: "ready",
      generatedAt: hoursAgo(31),
      requestedBy: "Dana K.",
    },
    {
      id: "rpt-2288",
      name: "Cost Allocation — August",
      templateId: "cost-allocation",
      period: "Last 30 days",
      format: "CSV",
      sizeKb: 0,
      status: "generating",
      generatedAt: hoursAgo(0.05),
      requestedBy: "Marco B.",
    },
    {
      id: "rpt-2287",
      name: "Security & RBAC Audit — Week 35",
      templateId: "security-audit",
      period: "Last 7 days",
      format: "PDF",
      sizeKb: 0,
      status: "failed",
      generatedAt: hoursAgo(52),
      requestedBy: "scheduler",
    },
    {
      id: "rpt-2286",
      name: "SLA / Uptime — August",
      templateId: "sla-uptime",
      period: "Last 30 days",
      format: "PDF",
      sizeKb: 611,
      status: "ready",
      generatedAt: hoursAgo(74),
      requestedBy: "scheduler",
    },
  ];
}

export function generateSchedules(): ReportSchedule[] {
  return [
    {
      id: "sch-11",
      name: "Weekly cluster health to platform-team",
      templateId: "cluster-health",
      cadence: "weekly",
      nextRun: hoursAhead(18),
      recipients: ["platform-team@example.com"],
      format: "PDF",
      enabled: true,
    },
    {
      id: "sch-12",
      name: "Monthly cost allocation to finops",
      templateId: "cost-allocation",
      cadence: "monthly",
      nextRun: hoursAhead(230),
      recipients: ["finops@example.com", "eng-leads@example.com"],
      format: "CSV",
      enabled: true,
    },
    {
      id: "sch-13",
      name: "Daily utilization snapshot",
      templateId: "resource-utilization",
      cadence: "daily",
      nextRun: hoursAhead(7),
      recipients: ["sre-oncall@example.com"],
      format: "CSV",
      enabled: false,
    },
    {
      id: "sch-14",
      name: "Quarterly security & RBAC audit",
      templateId: "security-audit",
      cadence: "quarterly",
      nextRun: hoursAhead(940),
      recipients: ["security@example.com"],
      format: "PDF",
      enabled: true,
    },
  ];
}

export function formatSize(sizeKb: number): string {
  if (sizeKb <= 0) return "—";
  if (sizeKb < 1024) return `${sizeKb} KB`;
  return `${(sizeKb / 1024).toFixed(1)} MB`;
}
