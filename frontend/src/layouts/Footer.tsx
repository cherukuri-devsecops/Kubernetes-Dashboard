export function Footer() {
  return (
    <footer className="border-t border-line px-4 py-4 text-xs text-content-muted sm:px-6 lg:px-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span>Kubernetes Dashboard</span>
        <span>Live cluster data · Kubernetes API, Prometheus, Loki, Tempo</span>
      </div>
    </footer>
  );
}
