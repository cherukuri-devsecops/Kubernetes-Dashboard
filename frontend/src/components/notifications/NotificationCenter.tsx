import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, Info, TriangleAlert, CircleCheck, CircleX } from "lucide-react";
import clsx from "clsx";

import { fetchNotifications, type NotificationItem } from "@/services/notifications";
import { formatRelativeTime } from "@/utils/format";

const KIND_ICON = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  error: CircleX,
} as const;

const KIND_COLOR = {
  info: "text-signal-blue",
  success: "text-signal-green",
  warning: "text-signal-amber",
  error: "text-signal-red",
} as const;

const REFRESH_INTERVAL_MS = 30000;
const READ_STORAGE_KEY = "dashboard.notifications.read";

/** Read state is per-browser: the cluster has no concept of an acknowledged
 * event, so dismissing one here must not pretend to change anything upstream. */
function loadReadIds(): Set<string> {
  try {
    const raw = window.localStorage.getItem(READ_STORAGE_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function persistReadIds(ids: Set<string>) {
  try {
    window.localStorage.setItem(READ_STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    // A browser blocking storage just means read state resets on reload.
  }
}

export function NotificationCenter() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [readIds, setReadIds] = useState<Set<string>>(loadReadIds);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((notification) => !readIds.has(notification.id)).length;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const items = await fetchNotifications();
        if (!cancelled) setNotifications(items);
      } catch {
        // The bell just stays at its last known state if a source is down.
      }
    }

    load();
    const id = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function markAsRead(id: string) {
    setReadIds((current) => {
      const next = new Set(current).add(id);
      persistReadIds(next);
      return next;
    });
  }

  function markAllAsRead() {
    setReadIds((current) => {
      const next = new Set(current);
      notifications.forEach((notification) => next.add(notification.id));
      persistReadIds(next);
      return next;
    });
  }

  function openNotification(notification: NotificationItem) {
    markAsRead(notification.id);
    setOpen(false);
    navigate(notification.href);
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Notifications"
        className="relative grid h-10 w-10 place-items-center rounded-md border border-line bg-surface text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
      >
        <Bell className="h-4 w-4" aria-hidden="true" />
        {unreadCount > 0 ? (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-signal-red px-1 text-[10px] font-semibold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 top-11 z-30 w-80 overflow-hidden rounded-md border border-line bg-surface shadow-panel">
          <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
            <p className="text-sm font-semibold text-content-primary">Notifications</p>
            <button
              type="button"
              onClick={markAllAsRead}
              className="flex items-center gap-1 text-xs text-content-muted transition hover:text-content-primary"
            >
              <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Mark all read
            </button>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-content-muted">
                No firing alerts or warning events.
              </p>
            ) : (
              notifications.map((notification) => {
                const Icon = KIND_ICON[notification.kind];
                const read = readIds.has(notification.id);
                return (
                  <button
                    key={notification.id}
                    type="button"
                    onClick={() => openNotification(notification)}
                    className={clsx(
                      "flex w-full items-start gap-3 border-b border-line px-3 py-3 text-left transition last:border-b-0 hover:bg-surface-hover",
                      read ? "opacity-60" : "",
                    )}
                  >
                    <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", KIND_COLOR[notification.kind])} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-content-primary">{notification.title}</p>
                        {!read ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" /> : null}
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-xs text-content-secondary">{notification.description}</p>
                      <p className="mt-1 text-[11px] text-content-muted">{formatRelativeTime(notification.createdAt)}</p>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
