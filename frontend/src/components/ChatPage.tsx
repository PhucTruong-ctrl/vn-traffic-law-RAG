"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "./AppHeader";
import ChatThread from "./ChatThread";
import Composer from "./Composer";
import Sidebar from "./Sidebar";
import SourceDrawer from "./SourceDrawer";
import Welcome from "./Welcome";
import type { ChatResponse, ConversationTurn } from "./chat-types";
import type { ProgressEvent } from "./ProgressEvents";
import type { Citation } from "./CitationCard";

const API_PATH = "/api/v1/chat";
const isCitation = (value: unknown): value is Citation => {
  if (typeof value !== "object" || value === null) return false;
  const citation = value as Record<string, unknown>;
  return (
    (typeof citation.provision_id === "string" && Boolean(citation.provision_id.trim())) ||
    (typeof citation.document === "string" && Boolean(citation.document.trim()))
  );
};
const validateChatResponse = (payload: unknown): ChatResponse => {
  if (typeof payload !== "object" || payload === null)
    throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
  const value = payload as Record<string, unknown>;
  const NON_VERIFIED_STATUS: Record<string, true> = {
    GREETING: true,
    OUT_OF_SCOPE: true,
    CORPUS_NOT_COVERED: true,
    INSUFFICIENT_EVIDENCE: true,
    WORKFLOW_UNAVAILABLE: true,
  };
  if (typeof value.status === "string" && NON_VERIFIED_STATUS[value.status]) {
    return payload as ChatResponse;
  }
  const answer = value.answer;
  const citations = value.citations;
  const validAnswer = typeof answer === "string" && Boolean(answer.trim());
  const validCitations =
    Array.isArray(citations) && citations.length > 0 && citations.every(isCitation);
  const claims = value.claims;
  const validClaims =
    Array.isArray(claims) &&
    claims.length > 0 &&
    claims.every(
      (claim) =>
        typeof claim === "object" &&
        claim !== null &&
        typeof (claim as { claim?: unknown }).claim === "string" &&
        Boolean((claim as { claim: string }).claim.trim()),
    );
  if (
    (value.status === "VERIFIED" && validAnswer && validClaims && validCitations) ||
    (value.status === undefined && validAnswer && validCitations)
  ) {
    const normalizedClaims = validClaims
      ? (claims as ChatResponse["claims"])
      : (citations as Array<Record<string, unknown>>).map((citation) => ({
          claim:
            (typeof citation.excerpt === "string" && citation.excerpt) ||
            (typeof citation.source_text === "string" && citation.source_text) ||
            (typeof citation.snippet === "string" && citation.snippet) ||
            (typeof answer === "string" ? answer : ""),
        }));
    return {
      ...value,
      status: "VERIFIED",
      claims: normalizedClaims,
      citations: citations as Citation[],
    } as ChatResponse;
  }
  throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
};

function responseFromMessage(message: Record<string, unknown>): ChatResponse | null {
  const candidate = message.response ?? message.payload ?? message;
  try {
    return validateChatResponse(candidate);
  } catch {
    return null;
  }
}
function turnsFromConversation(value: unknown): ConversationTurn[] {
  if (!value || typeof value !== "object") return [];
  const raw = value as Record<string, unknown>;
  const messages = Array.isArray(raw.messages)
    ? raw.messages
    : Array.isArray(raw.turns)
      ? raw.turns
      : [];
  const turns: ConversationTurn[] = [];
  for (const item of messages) {
    if (!item || typeof item !== "object") continue;
    const message = item as Record<string, unknown>;
    if (
      typeof message.question === "string" &&
      message.response &&
      typeof message.response === "object"
    ) {
      const response = responseFromMessage(message);
      if (response) turns.push({ question: message.question, response });
      continue;
    }
    if (
      (message.role === "user" || message.type === "user") &&
      typeof message.content === "string"
    ) {
      const next = messages[turns.length + 1];
      if (next && typeof next === "object") {
        const response = responseFromMessage(next as Record<string, unknown>);
        if (response) turns.push({ question: message.content, response });
      }
    }
  }
  return turns;
}

export default function ChatPage({ conversationId }: { conversationId?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [question, setQuestion] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(conversationId));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [activeId, setActiveId] = useState(conversationId);
  const abortControllerRef = useRef<AbortController | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (!conversationId) {
      return () => controller.abort();
    }
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) setLoading(true);
    });
    fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!result.ok) throw new Error("Không thể tải cuộc trò chuyện.");
        return result.json();
      })
      .then((payload) => {
        setActiveId(conversationId);
        setTurns(turnsFromConversation(payload));
        setQuestion("");
        setSubmittedQuestion("");
        setError("");
        setLoading(false);
      })
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(
            loadError instanceof Error ? loadError.message : "Không thể tải cuộc trò chuyện.",
          );
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [conversationId]);

  const navigateTo = useCallback(
    (id?: string) => {
      const target = id ? `/chat/${encodeURIComponent(id)}` : "/chat";
      if (pathname !== target) router.push(target);
    },
    [pathname, router],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitted = question.trim();
    if (!submitted || loading) return;
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setProgressEvents([]);
    setLoading(true);
    setError("");
    setSubmittedQuestion(submitted);
    try {
      const result = await fetch(API_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: submitted,
          ...(activeId ? { conversation_id: activeId } : {}),
        }),
        signal: abortController.signal,
      });
      const payload = await result.json().catch(() => null);
      if (!result.ok) {
        const message =
          payload &&
          typeof payload === "object" &&
          "error" in payload &&
          payload.error &&
          typeof payload.error === "object" &&
          "message" in payload.error &&
          typeof payload.error.message === "string"
            ? payload.error.message
            : "Không thể xử lý câu hỏi.";
        throw new Error(message);
      }
      const nextResponse = validateChatResponse(payload);
      setTurns((previous) => [...previous, { question: submitted, response: nextResponse }]);
      setQuestion("");
      const returnedId =
        payload &&
        typeof payload === "object" &&
        typeof (payload as Record<string, unknown>).conversation_id === "string"
          ? (payload as Record<string, string>).conversation_id
          : activeId;
      if (returnedId && returnedId !== activeId) {
        setActiveId(returnedId);
        navigateTo(returnedId);
      }
    } catch (submissionError) {
      if (submissionError instanceof DOMException && submissionError.name === "AbortError") return;
      setError(
        submissionError instanceof Error ? submissionError.message : "Không thể xử lý câu hỏi.",
      );
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
        setLoading(false);
      }
    }
  }
  function stopSubmission() {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    abortControllerRef.current?.abort();
  }
  useEffect(() => () => stopSubmission(), []);
  const resetConversation = () => {
    stopSubmission();
    setQuestion("");
    setTurns([]);
    setSubmittedQuestion("");
    setError("");
    setActiveId(undefined);
    navigateTo();
  };
  const suggestions = [
    "Mức phạt khi vượt đèn đỏ là bao nhiêu?",
    "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?",
    "Có được dùng điện thoại khi đang lái xe không?",
  ];
  return (
    <main className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        activeConversationId={activeId}
        activeQuestion={submittedQuestion || turns.at(-1)?.question || ""}
        onNewChat={resetConversation}
        onSelectConversation={(id) => navigateTo(id)}
        onCollapsedChange={setSidebarCollapsed}
      />
      <section className="main-panel" aria-label="Khu vực tra cứu">
        <AppHeader />
        <div
          className={
            turns.length || loading || error ? "conversation has-messages" : "conversation"
          }
          aria-busy={loading}
        >
          {!conversationId && !turns.length && !loading && !error ? (
            <Welcome
              question={question}
              suggestions={suggestions}
              onQuestion={setQuestion}
              onSubmit={submit}
            />
          ) : (
            <ChatThread
              turns={turns}
              question={submittedQuestion}
              loading={loading}
              error={error}
              progressEvents={progressEvents}
              onOpenSource={setDrawerCitation}
            />
          )}
          {(conversationId || turns.length > 0 || loading || error) && (
            <div className="sticky-composer">
              <Composer
                id="question"
                value={question}
                onChange={setQuestion}
                onSubmit={submit}
                onStop={stopSubmission}
                loading={loading}
              />
            </div>
          )}
        </div>
      </section>
      <SourceDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} />
    </main>
  );
}

export { turnsFromConversation };
