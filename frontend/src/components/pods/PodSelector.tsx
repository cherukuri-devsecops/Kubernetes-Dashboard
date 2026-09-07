import clsx from "clsx";

import type { PodSelection } from "@/components/pods/usePodSelection";

export const podSelectClass =
  "h-8 min-w-0 rounded-md border border-line bg-surface-hover/60 px-2 text-xs text-content-primary outline-none focus:border-brand/50 focus:ring-2 focus:ring-brand/20";

type PodSelectorProps = {
  selection: PodSelection;
  /** Called before any change, so an open stream or shell can be torn down. */
  onBeforeChange?: () => void;
};

export function PodSelector({ selection, onBeforeChange }: PodSelectorProps) {
  const { namespaces, namespace, pods, pod, container, containerNames } = selection;

  return (
    <>
      <label className="flex items-center gap-1.5">
        <span className="text-xs text-content-muted">Namespace</span>
        <select
          value={namespace}
          onChange={(event) => {
            onBeforeChange?.();
            selection.setNamespace(event.target.value);
          }}
          className={podSelectClass}
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
            onBeforeChange?.();
            selection.setPod(event.target.value);
          }}
          disabled={!namespace}
          className={clsx(podSelectClass, "max-w-[18rem]", !namespace && "opacity-50")}
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
              onBeforeChange?.();
              selection.setContainer(event.target.value);
            }}
            className={podSelectClass}
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
    </>
  );
}
