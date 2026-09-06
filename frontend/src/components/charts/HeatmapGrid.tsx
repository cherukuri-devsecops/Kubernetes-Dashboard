import clsx from "clsx";

export type HeatmapColumn = {
  key: string;
  label: string;
  color: string;
  format: (value: number) => string;
};

export type HeatmapRow = {
  key: string;
  label: string;
  values: Record<string, number>;
};

type HeatmapGridProps = {
  columns: HeatmapColumn[];
  rows: HeatmapRow[];
  selectedKey?: string;
  onSelectRow?: (key: string) => void;
};

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const num = parseInt(clean, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

export function HeatmapGrid({ columns, rows, selectedKey, onSelectRow }: HeatmapGridProps) {
  const maxByColumn = new Map<string, number>(
    columns.map((col) => [col.key, Math.max(...rows.map((row) => row.values[col.key] ?? 0), 0.0001)]),
  );

  if (rows.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-content-muted">No data available.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] border-separate border-spacing-y-1 text-left text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-content-muted">
            <th className="px-2 py-1 font-medium">Name</th>
            {columns.map((col) => (
              <th key={col.key} className="px-2 py-1 font-medium">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              onClick={() => onSelectRow?.(row.key)}
              className={clsx(
                "cursor-pointer transition",
                selectedKey === row.key && "ring-2 ring-brand/50",
              )}
            >
              <td className="whitespace-nowrap rounded-l-md bg-surface-hover/60 px-2 py-2 text-content-primary">{row.label}</td>
              {columns.map((col, index) => {
                const value = row.values[col.key] ?? 0;
                const intensity = 0.12 + 0.75 * (value / (maxByColumn.get(col.key) ?? 1));
                const [r, g, b] = hexToRgb(col.color);
                return (
                  <td
                    key={col.key}
                    title={`${col.label}: ${col.format(value)}`}
                    className={clsx("px-2 py-2 text-content-primary", index === columns.length - 1 && "rounded-r-md")}
                    style={{ backgroundColor: `rgba(${r}, ${g}, ${b}, ${intensity})` }}
                  >
                    {col.format(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
