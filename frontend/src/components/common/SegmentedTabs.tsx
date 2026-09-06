import clsx from "clsx";

export type SegmentedOption<T extends string> = {
  key: T;
  label: string;
  count?: number;
};

type SegmentedTabsProps<T extends string> = {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (key: T) => void;
  size?: "sm" | "md";
};

export function SegmentedTabs<T extends string>({ options, value, onChange, size = "md" }: SegmentedTabsProps<T>) {
  return (
    <div className="flex flex-wrap items-center gap-0.5 rounded-md border border-line bg-surface-hover/60 p-0.5">
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          onClick={() => onChange(option.key)}
          className={clsx(
            "rounded transition",
            size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
            value === option.key
              ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
              : "text-content-muted hover:text-content-primary",
          )}
        >
          {option.label}
          {option.count !== undefined ? <span className="ml-1.5 text-content-muted">{option.count}</span> : null}
        </button>
      ))}
    </div>
  );
}
