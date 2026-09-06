import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, Settings, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

function initialsFor(name: string | undefined) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  const initials = parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "");
  return initials.join("") || "?";
}

export function UserMenu() {
  const { logout, user } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 items-center gap-2 rounded-md border border-line bg-surface px-2 pr-3 text-sm transition hover:bg-surface-hover"
      >
        <span className="grid h-7 w-7 place-items-center rounded-full bg-brand/[0.16] text-xs font-semibold text-brand-400">
          {initialsFor(user?.name)}
        </span>
        <span className="hidden max-w-32 truncate text-content-secondary sm:inline">{user?.name}</span>
        <ChevronDown className="h-3.5 w-3.5 text-content-muted" aria-hidden="true" />
      </button>

      {open ? (
        <div className="absolute right-0 top-11 z-30 w-64 overflow-hidden rounded-md border border-line bg-surface shadow-panel">
          <div className="border-b border-line px-3 py-3">
            <p className="truncate text-sm font-medium text-content-primary">{user?.name}</p>
            <p className="truncate text-xs text-content-muted">{user?.email}</p>
            <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-xs text-brand-400">
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
              {user?.role}
            </span>
          </div>
          <nav className="p-1">
            <Link
              to="/settings"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-md px-2.5 py-2 text-sm text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
              Settings
            </Link>
            <button
              type="button"
              onClick={logout}
              className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-signal-red transition hover:bg-signal-red/10"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign out
            </button>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
