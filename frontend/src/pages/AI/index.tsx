import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, MessageSquarePlus, Sparkles, User } from "lucide-react";
import clsx from "clsx";

import { askAssistant, fetchSuggestions } from "@/services/ai";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  sources?: string[];
};

type Conversation = {
  id: string;
  title: string;
  createdAt: Date;
  messages: ChatMessage[];
};

const FALLBACK_SUGGESTIONS = [
  "Why are pods restarting?",
  "Show me error logs",
  "Top CPU consuming namespaces",
  "Are all nodes ready?",
];

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text:
    "Hi — I answer from your cluster's live data. Ask about pods, CPU, memory, alerts, logs, " +
    "nodes, storage, traces, deployments, or RBAC.",
};

function newConversation(): Conversation {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    createdAt: new Date(),
    messages: [WELCOME_MESSAGE],
  };
}

function formatConversationTime(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function AIPage() {
  const [history, setHistory] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation>(() => newConversation());
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(FALLBACK_SUGGESTIONS);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSuggestions()
      .then((list) => setSuggestions(list.length > 0 ? list : FALLBACK_SUGGESTIONS))
      .catch(() => setSuggestions(FALLBACK_SUGGESTIONS));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [active.messages, thinking]);

  function updateActive(mutate: (conversation: Conversation) => Conversation) {
    setActive((current) => mutate(current));
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;

    updateActive((conversation) => ({
      ...conversation,
      title: conversation.title === "New conversation" ? trimmed.slice(0, 48) : conversation.title,
      messages: [...conversation.messages, { id: crypto.randomUUID(), role: "user", text: trimmed }],
    }));
    setInput("");
    setThinking(true);

    let reply: ChatMessage;
    try {
      const result = await askAssistant(trimmed);
      reply = { id: crypto.randomUUID(), role: "assistant", text: result.answer, sources: result.sources };
    } catch (exc) {
      reply = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: exc instanceof Error ? `I could not reach the cluster data: ${exc.message}` : "Something went wrong.",
      };
    }

    updateActive((conversation) => ({ ...conversation, messages: [...conversation.messages, reply] }));
    setThinking(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(input);
  }

  function startNewConversation() {
    setHistory((current) => (active.messages.length > 1 ? [active, ...current] : current));
    setActive(newConversation());
  }

  function openConversation(conversation: Conversation) {
    if (conversation.id === active.id) return;
    setHistory((current) => {
      const rest = current.filter((c) => c.id !== conversation.id);
      return active.messages.length > 1 ? [active, ...rest] : rest;
    });
    setActive(conversation);
  }

  return (
    <div className="mx-auto grid w-full max-w-[1500px] gap-4 xl:grid-cols-[220px_minmax(0,1fr)_240px]">
      <aside className="hidden flex-col gap-3 rounded-lg border border-line bg-surface p-3 xl:flex">
        <button
          type="button"
          onClick={startNewConversation}
          className="flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand px-3 text-xs font-semibold text-white transition hover:bg-brand-600"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
          New Conversation
        </button>
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-content-muted">Conversation History</p>
          {history.length === 0 ? (
            <p className="px-1 text-xs text-content-muted">No past conversations yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {history.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => openConversation(conversation)}
                    className="flex w-full flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
                  >
                    <span className="truncate">{conversation.title}</span>
                    <span className="text-[10px] text-content-muted">{formatConversationTime(conversation.createdAt)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <section className="flex flex-col gap-4">
        <div className="rounded-lg border border-line bg-surface p-5 shadow-panel">
          <p className="text-sm text-brand-400">AI</p>
          <h2 className="mt-1 text-xl font-semibold text-content-primary">Cluster assistant</h2>
          <p className="mt-1 text-sm text-content-muted">
            Answers are computed from live cluster data — the Kubernetes API, Prometheus, Loki, and Tempo.
          </p>
        </div>

        <div className="flex h-[32rem] flex-col rounded-lg border border-line bg-surface">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
            {active.messages.map((message) => (
              <div key={message.id} className={clsx("flex items-start gap-2.5", message.role === "user" ? "flex-row-reverse" : "")}>
                <div
                  className={clsx(
                    "grid h-8 w-8 shrink-0 place-items-center rounded-full",
                    message.role === "assistant" ? "bg-brand/[0.16] text-brand-400" : "bg-surface-hover text-content-secondary",
                  )}
                >
                  {message.role === "assistant" ? <Bot className="h-4 w-4" aria-hidden="true" /> : <User className="h-4 w-4" aria-hidden="true" />}
                </div>
                <div
                  className={clsx(
                    "max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm leading-6",
                    message.role === "assistant" ? "bg-surface-hover text-content-primary" : "bg-brand/[0.16] text-content-primary",
                  )}
                >
                  <p className="whitespace-pre-wrap">{message.text}</p>
                  {message.sources && message.sources.length > 0 ? (
                    <p className="mt-2 border-t border-line pt-1.5 text-[11px] text-content-muted">
                      Source: {message.sources.join(", ")}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
            {thinking ? (
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand/[0.16] text-brand-400">
                  <Bot className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="flex items-center gap-1 rounded-lg bg-surface-hover px-3.5 py-2.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-content-muted" />
                </div>
              </div>
            ) : null}
          </div>

          <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-line p-3">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about your cluster…"
              className="h-11 flex-1 rounded-md border border-line bg-surface-hover/60 px-3 text-sm text-content-primary outline-none placeholder:text-content-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/20"
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="h-11 rounded-md bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Send
            </button>
          </form>
        </div>
      </section>

      <aside className="hidden flex-col gap-2 rounded-lg border border-line bg-surface p-3 xl:flex">
        <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-content-muted">
          <Sparkles className="h-3 w-3 text-brand-400" aria-hidden="true" />
          Suggested Questions
        </p>
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => sendMessage(suggestion)}
            className="rounded-md border border-line px-2.5 py-2 text-left text-xs text-content-secondary transition hover:bg-surface-hover hover:text-content-primary"
          >
            {suggestion}
          </button>
        ))}
      </aside>
    </div>
  );
}
