import {
  Activity,
  Bell,
  Bot,
  FileText,
  Gauge,
  LayoutDashboard,
  LifeBuoy,
  ScrollText,
  Settings,
  ShieldCheck,
  Zap,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
};

export const navItems: NavItem[] = [
  {
    label: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
    description: "Cluster overview and health",
  },
  {
    label: "Metrics",
    href: "/metrics",
    icon: Gauge,
    description: "CPU, memory, network, and disk usage",
  },
  {
    label: "Logs",
    href: "/logs",
    icon: ScrollText,
    description: "Live log stream across workloads",
  },
  {
    label: "Traces",
    href: "/traces",
    icon: Activity,
    description: "Distributed request traces",
  },
  {
    label: "Events",
    href: "/events",
    icon: Zap,
    description: "Kubernetes event stream",
  },
  {
    label: "Alerts",
    href: "/alerts",
    icon: Bell,
    description: "Firing and resolved alert rules",
  },
  {
    label: "Incidents",
    href: "/incidents",
    icon: LifeBuoy,
    description: "Incident timeline, ownership, and resolution",
  },
  {
    label: "AI",
    href: "/ai",
    icon: Bot,
    description: "AI assistant for cluster questions",
  },
  {
    label: "Reports",
    href: "/reports",
    icon: FileText,
    description: "Generated reports, schedules, and exports",
  },
  {
    label: "Administration",
    href: "/admin",
    icon: ShieldCheck,
    description: "Users, RBAC, clusters, and audit log",
  },
  {
    label: "Settings",
    href: "/settings",
    icon: Settings,
    description: "Profile, appearance, and cluster settings",
  },
];

const labelByPath = new Map(navItems.map((item) => [item.href, item.label]));

/** Resolves a route pathname into a breadcrumb trail of { label, href }. */
export function getBreadcrumbTrail(pathname: string): { label: string; href: string }[] {
  const topLevel = labelByPath.get(pathname);
  if (topLevel) {
    return pathname === "/"
      ? [{ label: "Dashboard", href: "/" }]
      : [
          { label: "Dashboard", href: "/" },
          { label: topLevel, href: pathname },
        ];
  }

  const segments = pathname.split("/").filter(Boolean);
  const trail = [{ label: "Dashboard", href: "/" }];
  let accumulated = "";
  for (const segment of segments) {
    accumulated += `/${segment}`;
    const known = labelByPath.get(accumulated);
    trail.push({
      label: known ?? segment.charAt(0).toUpperCase() + segment.slice(1),
      href: accumulated,
    });
  }
  return trail;
}
