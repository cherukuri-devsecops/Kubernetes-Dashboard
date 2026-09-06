import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { chartAxisColor, chartGridColor, chartTooltipContentStyle, chartTooltipLabelStyle } from "@/components/charts/ChartCard";

export type BarPoint = { time: string; a: number; b: number };

type BarMetricChartProps = {
  color: string;
  unit: string;
  series: BarPoint[];
  labelA: string;
  labelB: string;
};

export function BarMetricChart({ color, unit, series, labelA, labelB }: BarMetricChartProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={series} margin={{ left: -20, right: 8, top: 8, bottom: 0 }} barGap={2}>
        <CartesianGrid stroke={chartGridColor} vertical={false} />
        <XAxis dataKey="time" tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={{ stroke: chartGridColor }} tickLine={false} minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: chartAxisColor }} axisLine={false} tickLine={false} unit={unit} width={52} />
        <Tooltip
          contentStyle={chartTooltipContentStyle}
          labelStyle={chartTooltipLabelStyle}
          formatter={(value) => [`${value}${unit}`, ""]}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: chartAxisColor }} iconType="circle" iconSize={8} />
        <Bar dataKey="a" name={labelA} fill={color} fillOpacity={1} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="b" name={labelB} fill={color} fillOpacity={0.4} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
