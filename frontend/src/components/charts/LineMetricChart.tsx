import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { chartAxisColor, chartGridColor, chartTooltipContentStyle, chartTooltipLabelStyle } from "@/components/charts/ChartCard";

export type LinePoint = { time: string; value: number };

type LineMetricChartProps = {
  color: string;
  unit: string;
  series: LinePoint[];
  label?: string;
};

export function LineMetricChart({ color, unit, series, label }: LineMetricChartProps) {
  const gradientId = `line-metric-${color.replace("#", "")}`;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={series} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={chartGridColor} vertical={false} />
        <XAxis dataKey="time" tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={{ stroke: chartGridColor }} tickLine={false} minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={false} tickLine={false} unit={unit} width={52} />
        <Tooltip
          contentStyle={chartTooltipContentStyle}
          labelStyle={chartTooltipLabelStyle}
          formatter={(value) => [`${value}${unit}`, label ?? ""]}
        />
        <Area type="monotone" dataKey="value" name={label} stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
