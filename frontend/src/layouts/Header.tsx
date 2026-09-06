import { NavLink } from "react-router-dom";
import clsx from "clsx";

import { navItems } from "@/utils/navigation";
import { Breadcrumbs } from "@/components/common/Breadcrumbs";
import { NotificationCenter } from "@/components/notifications/NotificationCenter";
import { SearchBar } from "@/components/common/SearchBar";
import { ThemeSwitcher } from "@/components/common/ThemeSwitcher";
import { UserMenu } from "@/components/common/UserMenu";

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-app/86 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex flex-col gap-3">
        <div className="flex min-h-11 items-center justify-between gap-3">
          <Breadcrumbs />

          <div className="flex items-center gap-2">
            <SearchBar />
            <NotificationCenter />
            <ThemeSwitcher />
            <UserMenu />
          </div>
        </div>

        <nav className="-mx-1 flex gap-1 overflow-x-auto pb-1 lg:hidden">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.href}
                to={item.href}
                end={item.href === "/"}
                className={({ isActive }) =>
                  clsx(
                    "flex h-10 shrink-0 items-center gap-2 rounded-md px-3 text-sm",
                    isActive
                      ? "bg-brand/[0.16] text-content-primary ring-1 ring-brand/40"
                      : "text-content-muted hover:bg-surface-hover hover:text-content-primary",
                  )
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
