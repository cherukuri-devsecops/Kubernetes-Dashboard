import { NavLink } from "react-router-dom";
import clsx from "clsx";

import { navItems } from "@/utils/navigation";

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-line bg-surface px-5 py-6 shadow-panel lg:flex lg:flex-col">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="Kubernetes Dashboard"
            className="h-10 w-10 rounded-lg object-contain"
          />
          <div>
            <p className="text-sm font-semibold text-content-primary">Kubernetes</p>
            <p className="text-xs text-content-muted">Dashboard</p>
          </div>
        </div>
      </div>

      <nav className="mb-4 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.href}
              to={item.href}
              end={item.href === "/"}
              title={item.description}
              className={({ isActive }) =>
                clsx(
                  "flex h-11 items-center gap-3 rounded-md px-3 text-sm transition",
                  isActive
                    ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                    : "text-content-muted hover:bg-surface-hover hover:text-content-primary",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="rounded-md border border-line bg-surface-hover/60 p-3 text-xs text-content-muted">
        <div className="mb-2 flex items-center justify-between">
          <span>Environment</span>
          <span className="rounded-full bg-signal-green/10 px-2 py-0.5 text-signal-green">
            dev
          </span>
        </div>
        <div className="h-1.5 rounded-full bg-line">
          <div className="h-1.5 w-2/3 rounded-full bg-signal-green" />
        </div>
      </div>
    </aside>
  );
}
