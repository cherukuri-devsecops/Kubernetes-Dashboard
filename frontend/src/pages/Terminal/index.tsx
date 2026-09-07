import { useEffect, useState } from "react";

import { PodSelector } from "@/components/pods/PodSelector";
import { usePodSelection } from "@/components/pods/usePodSelection";
import { PodTerminal } from "@/components/terminal/PodTerminal";
import { fetchExecConfig, type ExecConfig } from "@/services/exec";

/** Standalone route for the pod shell. The same terminal also lives as a mode on
 * the Logs page, which is where the sidebar sends you; this route stays so a
 * direct link to /terminal keeps working. */
export function TerminalPage() {
  const [config, setConfig] = useState<ExecConfig | null>(null);
  const selection = usePodSelection(config?.allowedNamespaces ?? []);

  useEffect(() => {
    fetchExecConfig()
      .then(setConfig)
      .catch(() => setConfig({ enabled: false, allowedNamespaces: [], shells: [] }));
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <div>
        <p className="text-sm text-brand-400">Terminal</p>
        <h2 className="mt-0.5 text-xl font-semibold text-content-primary">Pod terminal</h2>
        <p className="mt-0.5 text-xs text-content-muted">
          An interactive shell inside a running container, the same as <code>kubectl exec -it</code>. Every session is
          recorded in the backend audit log.
        </p>
      </div>

      <PodTerminal
        namespace={selection.namespace}
        pod={selection.pod}
        container={selection.container}
        config={config}
        controls={<PodSelector selection={selection} />}
      />
    </div>
  );
}
