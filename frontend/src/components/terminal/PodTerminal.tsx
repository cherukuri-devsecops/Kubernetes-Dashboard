import { useEffect, useRef, useState } from "react";
import { Plug, PlugZap, ShieldAlert, TerminalSquare } from "lucide-react";
import clsx from "clsx";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

import { openExecSession, type ExecConfig, type ExecSession } from "@/services/exec";

// Matches the app's dark surface so the terminal doesn't look pasted on.
const TERMINAL_THEME = {
  background: "#11141b",
  foreground: "#d6dae4",
  cursor: "#31d0aa",
  selectionBackground: "#2a3040",
};

export function ExecDisabledNotice() {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4">
      <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-signal-amber" aria-hidden="true" />
      <div className="text-sm text-content-secondary">
        <p className="font-medium text-content-primary">Pod exec is disabled on this deployment.</p>
        <p className="mt-1">
          Enable it with <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">exec.enabled=true</code> in the
          Helm values. That grants the dashboard <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">create</code>{" "}
          on <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">pods/exec</code>, which lets anyone who can
          sign in run commands in any pod it can reach.
        </p>
      </div>
    </div>
  );
}

type PodTerminalProps = {
  namespace: string;
  pod: string;
  container?: string;
  config: ExecConfig | null;
  /** Rendered inline with the connect button — normally the pod selectors. */
  controls?: React.ReactNode;
};

export function PodTerminal({ namespace, pod, container, config, controls }: PodTerminalProps) {
  const [connected, setConnected] = useState(false);

  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const sessionRef = useRef<ExecSession | null>(null);

  const enabled = config?.enabled ?? false;

  useEffect(() => {
    if (!enabled || !hostRef.current || termRef.current) return;

    const term = new Terminal({
      convertEol: true,
      cursorBlink: true,
      fontSize: 12,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
      theme: TERMINAL_THEME,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(hostRef.current);
    fit.fit();
    term.writeln("Select a namespace and pod, then connect.");
    term.onData((data) => sessionRef.current?.send(data));

    termRef.current = term;
    fitRef.current = fit;

    const onResize = () => {
      fit.fit();
      sessionRef.current?.resize(term.rows, term.cols);
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      sessionRef.current?.close();
      sessionRef.current = null;
      term.dispose();
      termRef.current = null;
    };
  }, [enabled]);

  // Never leave a shell running in the cluster after this unmounts.
  useEffect(() => () => sessionRef.current?.close(), []);

  function disconnect() {
    sessionRef.current?.close();
    sessionRef.current = null;
    setConnected(false);
  }

  function connect() {
    const term = termRef.current;
    if (!term || !namespace || !pod) return;

    sessionRef.current?.close();
    term.clear();
    term.writeln(`Connecting to ${namespace}/${pod}${container ? `/${container}` : ""}…`);

    const session = openExecSession({
      namespace,
      pod,
      container: container || undefined,
      onOutput: (chunk) => term.write(chunk),
      onClose: (reason) => {
        setConnected(false);
        sessionRef.current = null;
        term.writeln(`\r\n\x1b[33m— session closed: ${reason} —\x1b[0m`);
      },
    });

    sessionRef.current = session;
    setConnected(true);
    // Tell the pod the real window size once the socket is up.
    window.setTimeout(() => {
      fitRef.current?.fit();
      session.resize(term.rows, term.cols);
      term.focus();
    }, 250);
  }

  if (config && !enabled) return <ExecDisabledNotice />;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3">
        {controls}
        <button
          type="button"
          onClick={connected ? disconnect : connect}
          disabled={!namespace || !pod}
          className={clsx(
            "flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
            connected
              ? "border border-line text-content-secondary hover:bg-surface-hover hover:text-content-primary"
              : "bg-brand text-white hover:bg-brand-600",
          )}
        >
          {connected ? <Plug className="h-3.5 w-3.5" aria-hidden="true" /> : <PlugZap className="h-3.5 w-3.5" aria-hidden="true" />}
          {connected ? "Disconnect" : "Connect"}
        </button>

        <span className="ml-auto flex items-center gap-1.5 text-xs text-content-muted">
          <TerminalSquare className="h-3.5 w-3.5" aria-hidden="true" />
          {connected ? (
            <>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal-green" />
              connected
            </>
          ) : (
            "not connected"
          )}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-[#11141b] p-2">
        <div ref={hostRef} className="h-[32rem] w-full" />
      </div>
    </div>
  );
}
