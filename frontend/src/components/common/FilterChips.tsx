import clsx from "clsx";

type FilterChipsProps<T extends string> = {
  label?: string;
  options: { key: T; label: string }[];
  selected: Set<T>;
  onToggle: (key: T) => void;
};

/** Multi-select pill row — every chip in `selected` is active, the rest are muted outlines. */
export function FilterChips<T extends string>({ label, options, selected, onToggle }: FilterChipsProps<T>) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {label ? <span className="text-xs text-content-muted">{label}</span> : null}
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          onClick={() => onToggle(option.key)}
          className={clsx(
            "rounded-full border px-2.5 py-1 text-xs font-medium transition",
            selected.has(option.key)
              ? "border-brand/40 bg-brand/10 text-brand-400"
              : "border-line text-content-muted hover:text-content-primary",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
