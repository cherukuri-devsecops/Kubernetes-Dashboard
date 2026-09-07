import { apiFetch } from "@/api/client";

export type ClusterInfo = {
  gitVersion: string;
  platform: string;
  nodeCount: number;
  readyNodeCount: number;
  namespaceCount: number;
  podCount: number;
};

export type K8sNode = {
  name: string;
  status: "Ready" | "NotReady";
  roles: string[];
  kubeletVersion: string | null;
  osImage: string | null;
  internalIp: string | null;
  cpuCapacity: string | null;
  memoryCapacity: string | null;
  cpuAllocatable: string | null;
  memoryAllocatable: string | null;
  podCapacity: string | null;
  createdAt: string | null;
};

export type K8sNamespace = {
  name: string;
  status: string;
  createdAt: string | null;
};

export type K8sPod = {
  name: string;
  namespace: string;
  status: string;
  ready: string;
  restarts: number;
  node: string | null;
  podIp: string | null;
  /** Container images. Use containerNames to address a container. */
  containers: string[];
  containerNames: string[];
  createdAt: string | null;
};

export type K8sDeployment = {
  name: string;
  namespace: string;
  replicas: number;
  readyReplicas: number;
  updatedReplicas: number;
  availableReplicas: number;
  images: string[];
  createdAt: string | null;
};

export type K8sService = {
  name: string;
  namespace: string;
  type: string;
  clusterIp: string | null;
  externalIps: string[];
  ports: string[];
  createdAt: string | null;
};

export type K8sStatefulSet = {
  name: string;
  namespace: string;
  replicas: number;
  readyReplicas: number;
  currentReplicas: number;
  serviceName: string | null;
  createdAt: string | null;
};

export type K8sDaemonSet = {
  name: string;
  namespace: string;
  desiredScheduled: number;
  currentScheduled: number;
  numberReady: number;
  numberAvailable: number;
  createdAt: string | null;
};

export type K8sJob = {
  name: string;
  namespace: string;
  completions: number | null;
  succeeded: number;
  failed: number;
  active: number;
  startTime: string | null;
  completionTime: string | null;
  createdAt: string | null;
};

export type K8sPvc = {
  name: string;
  namespace: string;
  status: string;
  volumeName: string | null;
  capacity: string | null;
  accessModes: string[];
  storageClass: string | null;
  createdAt: string | null;
};

function withNamespace(path: string, namespace: string | null): string {
  return namespace ? `${path}?namespace=${encodeURIComponent(namespace)}` : path;
}

export const fetchClusterInfo = () => apiFetch<ClusterInfo>("/api/k8s/cluster");
export const fetchNodes = () => apiFetch<K8sNode[]>("/api/k8s/nodes");
export const fetchNamespaces = () => apiFetch<K8sNamespace[]>("/api/k8s/namespaces");
export const fetchPods = (namespace: string | null) => apiFetch<K8sPod[]>(withNamespace("/api/k8s/pods", namespace));
export const fetchDeployments = (namespace: string | null) =>
  apiFetch<K8sDeployment[]>(withNamespace("/api/k8s/deployments", namespace));
export const fetchServices = (namespace: string | null) =>
  apiFetch<K8sService[]>(withNamespace("/api/k8s/services", namespace));
export const fetchStatefulSets = (namespace: string | null) =>
  apiFetch<K8sStatefulSet[]>(withNamespace("/api/k8s/statefulsets", namespace));
export const fetchDaemonSets = (namespace: string | null) =>
  apiFetch<K8sDaemonSet[]>(withNamespace("/api/k8s/daemonsets", namespace));
export const fetchJobs = (namespace: string | null) => apiFetch<K8sJob[]>(withNamespace("/api/k8s/jobs", namespace));
export const fetchPvcs = (namespace: string | null) => apiFetch<K8sPvc[]>(withNamespace("/api/k8s/pvcs", namespace));
