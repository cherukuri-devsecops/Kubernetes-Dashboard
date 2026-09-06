import { apiFetch } from "@/api/client";

export type SearchResult = {
  id: string;
  label: string;
  category: string;
  namespace: string | null;
  href: string;
};

export const searchCluster = (query: string, limit = 20) =>
  apiFetch<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`);
