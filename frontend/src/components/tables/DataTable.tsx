import type { ReactNode } from "react";
import clsx from "clsx";

export type Column<Row> = {
  key: string;
  header: string;
  /** Extra classes for the body cell — e.g. "text-content-primary" for the identifying column. */
  cellClassName?: string;
  render: (row: Row) => ReactNode;
};

type DataTableProps<Row> = {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  onRowClick?: (row: Row) => void;
  selectedKey?: string | null;
  emptyMessage?: string;
  /** Minimum table width in px before the container scrolls horizontally. */
  minWidth?: number;
};

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  emptyMessage = "No records found.",
  minWidth = 720,
}: DataTableProps<Row>) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-left text-sm" style={{ minWidth }}>
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-content-muted">
            {columns.map((column) => (
              <th key={column.key} className="py-2 pr-4 font-medium first:pl-4">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="py-8 text-center text-content-muted">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(
                    "transition",
                    onRowClick && "cursor-pointer hover:bg-surface-hover",
                    selectedKey === key && "bg-surface-hover",
                  )}
                >
                  {columns.map((column) => (
                    <td key={column.key} className={clsx("py-2.5 pr-4 text-content-secondary first:pl-4", column.cellClassName)}>
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
