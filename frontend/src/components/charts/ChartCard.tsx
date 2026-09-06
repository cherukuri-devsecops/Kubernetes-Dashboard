import type { ReactNode } from "react";

export const chartGridColor = "var(--color-border)";
export const chartAxisColor = "var(--color-text-muted)";
export const chartTooltipContentStyle = {
  backgroundColor: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: 8,
  color: "var(--color-text-primary)",
  fontSize: 12,
};
export const chartTooltipLabelStyle = { color: "var(--color-text-muted)" };

// Fixed categorical order, validated for CVD separation via the dataviz skill's
// validate_palette.js (worst-pair deutan ΔE 11.4, within the 8-12 floor band -
// legal with the legends/direct labels this app already uses on every chart).
export const metricColors = {
  cpu: "#31d0aa",
  memory: "#6ea8fe",
  network: "#d95926",
  disk: "#c98500",
} as const;

// Event type pair, validated on both surfaces with validate_palette.js: all six
// checks pass (worst protan ΔE 26.0, normal-vision ΔE 28.6, contrast >= 3:1 light
// and dark). Amber stays the warning hue the badges already use.
export const eventColors = {
  normal: "#4a90e2",
  warning: "#c98500",
} as const;

type ChartCardProps = {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  height?: number;
  children: ReactNode;
};

export function ChartCard({ title, subtitle, action, height = 220, children }: ChartCardProps) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-content-primary">{title}</h3>
          {subtitle ? <p className="text-xs text-content-muted">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      <div style={{ height }}>{children}</div>
    </section>
  );
}
