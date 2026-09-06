import { RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";

type GaugeChartProps = {
  value: number;
  color: string;
  label: string;
  sublabel?: string;
};

export function GaugeChart({ value, color, label, sublabel }: GaugeChartProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const data = [{ name: label, value: clamped, fill: color }];

  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-line bg-surface p-4">
      <div className="relative h-32 w-32">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            data={data}
            innerRadius="72%"
            outerRadius="100%"
            startAngle={90}
            endAngle={-270}
            barSize={10}
          >
            <RadialBar
              dataKey="value"
              cornerRadius={4}
              background={{ fill: "var(--color-border)" }}
              isAnimationActive={false}
            />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold text-content-primary">{clamped.toFixed(1)}%</span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-content-primary">{label}</p>
        {sublabel ? <p className="text-xs text-content-muted">{sublabel}</p> : null}
      </div>
    </div>
  );
}
