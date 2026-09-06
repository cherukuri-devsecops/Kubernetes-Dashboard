import { apiFetch } from "@/api/client";

/** Kubernetes has no User object — an identity exists only because a
 * RoleBinding names it, which is what these endpoints report. */

export type SubjectKind = "User" | "Group" | "ServiceAccount" | string;

export type SubjectRole = {
  role: string;
  kind: string;
  binding: string;
  scope: string;
};

export type RbacSubject = {
  id: string;
  kind: SubjectKind;
  name: string;
  namespace: string | null;
  roles: SubjectRole[];
  namespaces: string[];
  roleCount: number;
  clusterWide: boolean;
  isDefault: boolean;
};

export type PolicyRule = {
  apiGroups: string[];
  resources: string[];
  verbs: string[];
  resourceNames: string[];
  nonResourceUrls: string[];
};

export type RbacRole = {
  name: string;
  kind: "ClusterRole" | "Role";
  namespace: string | null;
  scope: string;
  rules: PolicyRule[];
  ruleCount: number;
  resources: string[];
  access: "read" | "write";
  isDefault: boolean;
  createdAt: string | null;
};

export type RoleBinding = {
  name: string;
  kind: "ClusterRoleBinding" | "RoleBinding";
  namespace: string | null;
  scope: string;
  roleKind: string;
  roleName: string;
  subjects: { kind: string; name: string; namespace: string | null }[];
  isDefault: boolean;
  createdAt: string | null;
};

export type ServiceAccount = {
  name: string;
  namespace: string;
  secrets: string[];
  imagePullSecrets: string[];
  automountToken: boolean;
  createdAt: string | null;
};

export const fetchSubjects = () => apiFetch<RbacSubject[]>("/api/k8s/subjects");
export const fetchRoles = () => apiFetch<RbacRole[]>("/api/k8s/roles");
export const fetchRoleBindings = () => apiFetch<RoleBinding[]>("/api/k8s/rolebindings");
export const fetchServiceAccounts = () => apiFetch<ServiceAccount[]>("/api/k8s/serviceaccounts");
