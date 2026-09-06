import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { CornerDownLeft, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";

import { navItems } from "@/utils/navigation";
import { searchCluster, type SearchResult } from "@/services/search";

const pageResults: SearchResult[] = navItems.map((item) => ({
  id: `page:${item.href}`,
  label: item.label,
  category: "Page",
  namespace: null,
  href: item.href,
}));

const SEARCH_DEBOUNCE_MS = 200;

export function SearchBar() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const [clusterResults, setClusterResults] = useState<SearchResult[]>([]);

  // Cluster objects are searched server-side; pages are matched locally.
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setClusterResults([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchCluster(trimmed, 15)
        .then((results) => {
          if (!cancelled) setClusterResults(results);
        })
        .catch(() => {
          if (!cancelled) setClusterResults([]);
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  const results = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return pageResults;
    const pages = pageResults.filter((result) => result.label.toLowerCase().includes(trimmed));
    return [...pages, ...clusterResults];
  }, [query, clusterResults]);

  useEffect(() => {
    setActiveIndex(0);
  }, [results]);

  useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
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

  function selectResult(result: SearchResult) {
    navigate(result.href);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, results.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      const result = results[activeIndex];
      if (result) selectResult(result);
    }
  }

  return (
    <div ref={containerRef} className="relative hidden min-w-64 md:block">
      <div className="flex h-10 items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm text-content-muted focus-within:border-brand/50 focus-within:ring-2 focus-within:ring-brand/20">
        <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          placeholder="Search pods, deployments, pages…"
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          className="w-full bg-transparent text-content-primary outline-none placeholder:text-content-muted"
        />
        <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] text-content-muted lg:inline-block">
          ⌘K
        </kbd>
      </div>

      {open && results.length > 0 ? (
        <div className="absolute left-0 right-0 top-11 z-30 max-h-80 overflow-y-auto rounded-md border border-line bg-surface shadow-panel">
          {results.map((result, index) => (
            <button
              key={result.id}
              type="button"
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => selectResult(result)}
              className={clsx(
                "flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition",
                index === activeIndex ? "bg-surface-hover text-content-primary" : "text-content-secondary",
              )}
            >
              <span className="truncate">
                {result.label}
                {result.namespace ? <span className="text-content-muted"> · {result.namespace}</span> : null}
              </span>
              <span className="flex shrink-0 items-center gap-1.5 text-xs text-content-muted">
                {result.category}
                {index === activeIndex ? <CornerDownLeft className="h-3 w-3" aria-hidden="true" /> : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
