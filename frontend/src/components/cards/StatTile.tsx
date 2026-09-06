import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export type StatTone = "green" | "amber" | "red" | "blue" | "violet" | "neutral";

const TONE_CLASSES: Record<StatTone, string> = {
  green: "bg-signal-green/10 text-signal-green",
  amber: "bg-signal-amber/10 text-signal-amber",
  red: "bg-signal-red/10 text-signal-red",
  blue: "bg-signal-blue/10 text-signal-blue",
  violet: "bg-brand/10 text-brand-400",
  neutral: "bg-surface-hover text-content-secondary",
};

type StatTileProps = {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: StatTone;
  hint?: string;
};

export function StatTile({ label, value, icon: Icon, tone = "neutral", hint }: StatTileProps) {
  return (
    <article className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className={clsx("grid h-10 w-10 place-items-center rounded-md", TONE_CLASSES[tone])}>
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        {hint ? <span className="text-xs text-content-muted">{hint}</span> : null}
      </div>
      <p className="text-2xl font-semibold text-content-primary">{value}</p>
      <h3 className="mt-1 text-sm text-content-secondary">{label}</h3>
    </article>
  );
}
