import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

export type DonutSegment = {
  key: string;
  label: string;
  value: number;
  color: string;
};

type DonutChartProps = {
  segments: DonutSegment[];
  centerLabel?: string;
};

export function DonutChart({ segments, centerLabel = "Total" }: DonutChartProps) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);

  return (
    <div className="flex items-center gap-4">
      <div className="relative h-28 w-28 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={segments}
              dataKey="value"
              nameKey="label"
              innerRadius="70%"
              outerRadius="100%"
              paddingAngle={total > 0 ? 2 : 0}
              startAngle={90}
              endAngle={-270}
              isAnimationActive={false}
            >
              {segments.map((segment) => (
                <Cell key={segment.key} fill={segment.color} stroke="none" />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold text-content-primary">{total}</span>
          <span className="text-[11px] text-content-muted">{centerLabel}</span>
        </div>
      </div>
      <ul className="flex-1 space-y-1.5">
        {segments.map((segment) => (
          <li key={segment.key} className="flex items-center justify-between gap-3 text-xs">
            <span className="flex items-center gap-1.5 text-content-secondary">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: segment.color }} />
              {segment.label}
            </span>
            <span className="text-content-primary">
              {segment.value}
              <span className="ml-1 text-content-muted">
                ({total > 0 ? Math.round((segment.value / total) * 100) : 0}%)
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
