import { useEffect, useMemo, useRef, useState } from "react";
import { Plug, PlugZap, ShieldAlert, TerminalSquare } from "lucide-react";
import clsx from "clsx";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

import { fetchNamespaces, fetchPods, type K8sPod } from "@/services/kubernetes";
import { fetchExecConfig, openExecSession, type ExecConfig, type ExecSession } from "@/services/exec";

const selectClass =
  "h-8 min-w-0 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20";

// Matches the app's dark surface so the terminal doesn't look pasted on.
const TERMINAL_THEME = {
  background: "#11141b",
  foreground: "#d6dae4",
  cursor: "#31d0aa",
  selectionBackground: "#2a3040",
};

export function TerminalPage() {
  const [config, setConfig] = useState<ExecConfig | null>(null);
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [namespace, setNamespace] = useState("");
  const [pods, setPods] = useState<K8sPod[]>([]);
  const [pod, setPod] = useState("");
  const [container, setContainer] = useState("");
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const sessionRef = useRef<ExecSession | null>(null);

  useEffect(() => {
    fetchExecConfig()
      .then(setConfig)
      .catch(() => setConfig({ enabled: false, allowedNamespaces: [], shells: [] }));
  }, []);

  useEffect(() => {
    if (!config?.enabled) return;
    fetchNamespaces()
      .then((list) => {
        const names = list.map((item) => item.name);
        const allowed = config.allowedNamespaces;
        setNamespaces(allowed.length > 0 ? names.filter((name) => allowed.includes(name)) : names);
      })
      .catch(() => setNamespaces([]));
  }, [config]);

  useEffect(() => {
    if (!namespace) {
      setPods([]);
      return;
    }
    let cancelled = false;
    fetchPods(namespace)
      .then((list) => {
        if (cancelled) return;
        setPods(list);
        setPod((current) => (list.some((item) => item.name === current) ? current : ""));
      })
      .catch(() => {
        if (!cancelled) setPods([]);
      });
    return () => {
      cancelled = true;
    };
  }, [namespace]);

  const containerNames = useMemo(
    () => pods.find((item) => item.name === pod)?.containerNames ?? [],
    [pods, pod],
  );

  // Build the terminal once the feature is known to be available.
  useEffect(() => {
    if (!config?.enabled || !hostRef.current || termRef.current) return;

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
      term.dispose();
      termRef.current = null;
    };
  }, [config]);

  // Never leave a shell running in the cluster after the page goes away.
  useEffect(() => () => sessionRef.current?.close(), []);

  function connect() {
    const term = termRef.current;
    if (!term || !namespace || !pod) return;

    sessionRef.current?.close();
    term.clear();
    term.writeln(`Connecting to ${namespace}/${pod}${container ? `/${container}` : ""}…`);
    setStatus(null);

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

  function disconnect() {
    sessionRef.current?.close();
    sessionRef.current = null;
    setConnected(false);
  }

  if (config && !config.enabled) {
    return (
      <div className="mx-auto flex w-full max-w-[900px] flex-col gap-4">
        <div>
          <p className="text-sm text-brand-400">Terminal</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Pod terminal</h2>
        </div>
        <div className="flex items-start gap-3 rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-signal-amber" aria-hidden="true" />
          <div className="text-sm text-content-secondary">
            <p className="font-medium text-content-primary">Pod exec is disabled on this deployment.</p>
            <p className="mt-1">
              Enable it with <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">exec.enabled=true</code> in the
              Helm values. That grants the dashboard <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">create</code>{" "}
              on <code className="rounded bg-surface-hover px-1 py-0.5 text-xs">pods/exec</code>, which lets anyone who can
              sign in run commands in any pod it can reach — so restrict dashboard login first.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-brand-400">Terminal</p>
          <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Pod terminal</h2>
          <p className="mt-0.5 text-xs text-content-muted">
            An interactive shell inside a running container, the same as <code>kubectl exec -it</code>. Every session is
            recorded in the backend audit log.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3">
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-content-muted">Namespace</span>
          <select
            value={namespace}
            onChange={(event) => {
              disconnect();
              setNamespace(event.target.value);
              setPod("");
              setContainer("");
            }}
            className={selectClass}
          >
            <option value="">Select…</option>
            {namespaces.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5">
          <span className="text-xs text-content-muted">Pod</span>
          <select
            value={pod}
            onChange={(event) => {
              disconnect();
              setPod(event.target.value);
              setContainer("");
            }}
            disabled={!namespace}
            className={clsx(selectClass, "max-w-[18rem]", !namespace && "opacity-50")}
          >
            <option value="">Select…</option>
            {pods.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        {containerNames.length > 1 ? (
          <label className="flex items-center gap-1.5">
            <span className="text-xs text-content-muted">Container</span>
            <select
              value={container}
              onChange={(event) => {
                disconnect();
                setContainer(event.target.value);
              }}
              className={selectClass}
            >
              <option value="">Default</option>
              {containerNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

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

      {status ? (
        <p className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-xs text-signal-red">{status}</p>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-line bg-[#11141b] p-2">
        <div ref={hostRef} className="h-[32rem] w-full" />
      </div>
    </div>
  );
}
