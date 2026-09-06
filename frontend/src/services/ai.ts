import { apiFetch } from "@/api/client";

export type AssistantReply = {
  answer: string;
  sources: string[];
  data: Record<string, unknown>;
  /** True when a data source the answer needed was unreachable. */
  degraded: boolean;
};

export const askAssistant = (question: string) =>
  apiFetch<AssistantReply>("/api/ai/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

export const fetchSuggestions = () => apiFetch<string[]>("/api/ai/suggestions");
