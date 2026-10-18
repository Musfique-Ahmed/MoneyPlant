"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { z } from "zod";
import { apiGet, apiPost } from "@/lib/api";
import { Business, Explanation, ProviderHealth } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Send, Server, Sparkles, TriangleAlert, RotateCcw, BookOpen } from "lucide-react";
import { useWorkspace } from "@/components/WorkspaceContext";

const ProviderList = z.array(ProviderHealth);

interface ChatTurn {
  role: "user" | "assistant" | "system";
  content: string;
  explanation?: z.infer<typeof Explanation> | null;
  error?: string | null;
  pending?: boolean;
}

const SUGGESTIONS = [
  "Why is my closing cash negative in Q2?",
  "Which inputs reduce direct costs the most without hurting quality?",
  "Compare the latest three scenarios on operating profit.",
  "What data am I missing for a confident decision?",
];

export default function AssistantPage() {
  const { businessId } = useWorkspace();
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = businessId ?? businesses.data?.[0]?.id ?? null;

  const providers = useQuery({
    queryKey: ["ai-health"],
    queryFn: () => apiGet("/api/ai/health", ProviderList),
    refetchInterval: 60_000,
  });

  const send = useMutation({
    mutationFn: async (message: string) => {
      if (!effectiveId) throw new Error("No business selected");
      const resp = await apiPost(
        "/api/ai/assistant/chat",
        { business_id: effectiveId, user_question: message },
        z.object({
          explanation: Explanation,
          provider: z.string(),
          model: z.string(),
          mode: z.string(),
        })
      );
      return resp.explanation;
    },
    onMutate: (message) => {
      const userTurn: ChatTurn = { role: "user", content: message };
      const pendingTurn: ChatTurn = { role: "assistant", content: "Thinking…", pending: true };
      setTurns((prev) => [...prev, userTurn, pendingTurn]);
      setDraft("");
    },
    onSuccess: (data) => {
      setTurns((prev) => {
        const next = [...prev];
        // Replace the last "pending" assistant turn
        for (let i = next.length - 1; i >= 0; i--) {
          const t = next[i];
          if (t && t.role === "assistant" && t.pending) {
            next[i] = {
              role: "assistant",
              content: data.summary ?? "(no summary returned)",
              explanation: data,
              error: data.status === "ok" ? null : (data.reason ?? "Provider did not return a usable response."),
            };
            break;
          }
        }
        return next;
      });
    },
    onError: (err) => {
      setTurns((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i--) {
          const t = next[i];
          if (t && t.role === "assistant" && t.pending) {
            next[i] = {
              role: "assistant",
              content: "Request failed.",
              error: String((err as Error).message),
            };
            break;
          }
        }
        return next;
      });
    },
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const activeMode = useMemo(() => {
    const ok = (providers.data ?? []).find((p) => p.status === "ok");
    return ok?.mode ?? null;
  }, [providers.data]);

  return (
    <div className="grid h-full grid-cols-1 gap-4 px-6 py-6 lg:grid-cols-[1fr_22rem]">
      <Card className="flex flex-col">
        <CardHeader
          title="Assistant"
          description={
            activeMode
              ? `Active provider: ${activeMode}. The assistant explains decisions; it does not change them.`
              : "No provider healthy. Check Settings or the provider panel."
          }
          actions={
            <Button
              variant="ghost"
              size="sm"
              iconLeft={<RotateCcw size={14} />}
              onClick={() => setTurns([])}
              disabled={turns.length === 0}
            >
              Reset
            </Button>
          }
        />
        <CardBody className="flex flex-1 flex-col">
          <div
            ref={scrollRef}
            className="flex-1 space-y-3 overflow-y-auto rounded-md border border-line bg-surface-sunken p-3"
            aria-live="polite"
          >
            {turns.length === 0 ? (
              <EmptyState
                title="Ask about your numbers"
                description="The assistant only sees the structured context for the active business. It cannot browse files or guess missing data."
                icon={<BookOpen size={20} />}
              />
            ) : (
              turns.map((t, i) => <Message key={i} turn={t} />)
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setDraft(s)}
                className="rounded-sm border border-line bg-surface-raised px-2 py-1 text-xs text-ink-muted hover:text-ink"
              >
                {s}
              </button>
            ))}
          </div>

          <form
            className="mt-3 flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const v = draft.trim();
              if (!v) return;
              send.mutate(v);
            }}
          >
            <div className="flex-1">
              <Input
                placeholder={
                  effectiveId
                    ? "Ask the assistant about your financial position, scenarios, or assumptions…"
                    : "Select a business first (top right)"
                }
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={!effectiveId || send.isPending}
              />
            </div>
            <Button
              type="submit"
              iconLeft={<Send size={14} />}
              disabled={!draft.trim() || !effectiveId}
              loading={send.isPending}
            >
              Send
            </Button>
          </form>
        </CardBody>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Provider status" description="Live health probes. No silent fallback." />
          <CardBody>
            {providers.isLoading ? (
              <Skeleton className="h-16" />
            ) : providers.isError ? (
              <ErrorState title="Could not load providers" />
            ) : !providers.data || providers.data.length === 0 ? (
              <p className="text-sm text-ink-muted">No providers are configured.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {providers.data.map((p) => (
                  <li
                    key={`${p.mode}-${p.model}`}
                    className="flex items-start justify-between gap-3 rounded border border-line p-2"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 font-medium">
                        <Server size={12} className="text-ink-subtle" />
                        {labelFor(p.mode)}
                      </div>
                      <div className="text-xs text-ink-subtle">{p.model}</div>
                      {p.detail && <div className="mt-1 text-xs text-ink-muted">{p.detail}</div>}
                      <div className="text-xs text-ink-subtle">
                        {p.latency_ms !== null && `~${p.latency_ms} ms · `}
                        checked {new Date(p.checked_at).toLocaleTimeString()}
                      </div>
                    </div>
                    <Badge tone={p.status === "ok" ? "ok" : p.status === "misconfigured" ? "warn" : "bad"}>
                      {p.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What the assistant can do" />
          <CardBody>
            <ul className="space-y-1 text-sm text-ink-muted">
              <li>· Read the active business’s financial summary.</li>
              <li>· Read rule verdicts and Laya assessments.</li>
              <li>· Reference up to the last few saved scenarios.</li>
              <li>· Suggest which inputs to revisit (without committing).</li>
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What it will not do" />
          <CardBody>
            <ul className="space-y-1 text-sm text-ink-muted">
              <li className="flex items-start gap-2">
                <TriangleAlert size={14} className="mt-0.5 shrink-0 text-warn" />
                Override rule verdicts or binding constraints.
              </li>
              <li className="flex items-start gap-2">
                <TriangleAlert size={14} className="mt-0.5 shrink-0 text-warn" />
                Fabricate numbers it cannot see in the structured context.
              </li>
              <li className="flex items-start gap-2">
                <TriangleAlert size={14} className="mt-0.5 shrink-0 text-warn" />
                Send data off-host when local mode is selected and healthy.
              </li>
            </ul>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Message({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-prose rounded-md bg-accent px-3 py-2 text-sm text-ink-inverse">
          {turn.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-prose rounded-md border border-line bg-surface-raised px-3 py-2 text-sm">
        <div className="mb-1 flex items-center gap-1 text-xs text-ink-muted">
          <Sparkles size={12} /> Assistant
          {turn.pending && <span>· thinking…</span>}
        </div>
        {turn.error ? (
          <div className="text-bad">{turn.error}</div>
        ) : (
          <>
            <p className="text-ink">{turn.content}</p>
            {turn.explanation && turn.explanation.status === "ok" && (
              <div className="mt-2 space-y-1 border-t border-line pt-2 text-xs text-ink-muted">
                {turn.explanation.next_actions.length > 0 && (
                  <div>
                    <span className="font-semibold text-ink">Next: </span>
                    {turn.explanation.next_actions.slice(0, 2).join(" · ")}
                  </div>
                )}
                {turn.explanation.limitations.length > 0 && (
                  <div>
                    <span className="font-semibold text-ink">Limits: </span>
                    {turn.explanation.limitations.slice(0, 2).join(" · ")}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function labelFor(mode: string): string {
  switch (mode) {
    case "local":
      return "Local (Ollama)";
    case "openai":
      return "OpenAI";
    case "anthropic":
      return "Anthropic";
    default:
      return mode;
  }
}
