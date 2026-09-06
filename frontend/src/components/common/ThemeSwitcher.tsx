import { Moon, Monitor, Sun } from "lucide-react";
import clsx from "clsx";

import { useTheme, type Theme } from "@/context/ThemeContext";

const options: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

type ThemeSwitcherProps = {
  showLabels?: boolean;
};

export function ThemeSwitcher({ showLabels = false }: ThemeSwitcherProps) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5"
    >
      {options.map((option) => {
        const Icon = option.icon;
        const isActive = theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            title={option.label}
            onClick={() => setTheme(option.value)}
            className={clsx(
              "flex h-9 items-center gap-2 rounded px-2.5 text-sm transition",
              showLabels ? "" : "justify-center",
              isActive
                ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                : "text-content-muted hover:bg-surface-hover hover:text-content-primary",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {showLabels ? <span>{option.label}</span> : <span className="sr-only">{option.label}</span>}
          </button>
        );
      })}
    </div>
  );
}
