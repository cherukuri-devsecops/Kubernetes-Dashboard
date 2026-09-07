import { useEffect, useMemo, useState } from "react";

import { fetchNamespaces, fetchPods, type K8sPod } from "@/services/kubernetes";

export type PodSelection = {
  namespaces: string[];
  namespace: string;
  pods: K8sPod[];
  pod: string;
  container: string;
  containerNames: string[];
  /** True once a namespace and pod are chosen, i.e. a target exists. */
  ready: boolean;
  setNamespace: (namespace: string) => void;
  setPod: (pod: string) => void;
  setContainer: (container: string) => void;
};

/** Namespace → pod → container selection, shared by the log tail and the shell
 * so switching between them keeps the pod you already picked. */
export function usePodSelection(allowedNamespaces: string[] = []): PodSelection {
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [namespace, setNamespaceState] = useState("");
  const [pods, setPods] = useState<K8sPod[]>([]);
  const [pod, setPodState] = useState("");
  const [container, setContainer] = useState("");

  useEffect(() => {
    fetchNamespaces()
      .then((list) => {
        const names = list.map((item) => item.name);
        setNamespaces(allowedNamespaces.length > 0 ? names.filter((n) => allowedNamespaces.includes(n)) : names);
      })
      .catch(() => setNamespaces([]));
    // allowedNamespaces is a stable config value; joining keeps the dep primitive.
  }, [allowedNamespaces.join(",")]);

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
        setPodState((current) => (list.some((item) => item.name === current) ? current : ""));
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

  return {
    namespaces,
    namespace,
    pods,
    pod,
    container,
    containerNames,
    ready: Boolean(namespace && pod),
    setNamespace: (next: string) => {
      setNamespaceState(next);
      setPodState("");
      setContainer("");
    },
    setPod: (next: string) => {
      setPodState(next);
      setContainer("");
    },
    setContainer,
  };
}
