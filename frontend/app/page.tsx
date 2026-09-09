"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import AppHeader from "../src/components/AppHeader";
import ChatThread from "../src/components/ChatThread";
import Composer from "../src/components/Composer";
import Sidebar from "../src/components/Sidebar";
import SourceDrawer from "../src/components/SourceDrawer";
import Welcome from "../src/components/Welcome";
import type {
  ChatResponse,
  Claim,
  ConversationTurn,
} from "../src/components/chat-types";
import type { ProgressEvent } from "../src/components/ProgressEvents";
import type { Citation } from "../src/components/CitationCard";

const API_PATH = "/api/v1/chat";
const isCitation = (value: unknown): value is Citation =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as Citation).provision_id === "string";
const validateChatResponse = (payload: unknown): ChatResponse => {
  if (typeof payload !== "object" || payload === null)
    throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
  const value = payload as Record<string, unknown>;
  if (
    value.status === "ABSTAINED" &&
    typeof value.abstention === "object" &&
    value.abstention !== null
  ) {
    const abstention = value.abstention as Record<string, unknown>;
    if (
      (typeof abstention.reason_code === "string" &&
        Boolean(abstention.reason_code.trim())) ||
      (typeof abstention.reason === "string" &&
        Boolean(abstention.reason.trim()))
    )
      return payload as ChatResponse;
  }
  const claims = value.claims;
  const citations = value.citations;
  if (
    value.status === "VERIFIED" &&
    typeof value.answer === "string" &&
    Boolean(value.answer.trim()) &&
    Array.isArray(claims) &&
    claims.length > 0 &&
    claims.every(
      (claim): claim is Claim =>
        typeof claim === "object" &&
        claim !== null &&
        typeof (claim as Claim).claim === "string" &&
        Boolean((claim as Claim).claim.trim()),
    ) &&
    Array.isArray(citations) &&
    citations.length > 0 &&
    citations.every(isCitation)
  )
    return payload as ChatResponse;
  throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitted = question.trim();
    if (!submitted || loading) return;
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setProgressEvents([]);
    setLoading(true);
    setError("");
    setResponse(null);
    setSubmittedQuestion(submitted);
    try {
      let payload: unknown = null;
      if (typeof EventSource !== "undefined") {
        try {
          payload = await new Promise<unknown>((resolve, reject) => {
            const source = new EventSource(
              `${API_PATH}/events?question=${encodeURIComponent(submitted)}`,
            );
            eventSourceRef.current = source;
            const timeout = window.setTimeout(() => {
              source.close();
              eventSourceRef.current = null;
              reject(new Error("SSE timeout"));
            }, 30_000);
            const handleEvent = (event: Event) => {
              const data = JSON.parse((event as MessageEvent).data) as ProgressEvent;
              setProgressEvents((previous) => [...previous, data]);
            };
            source.addEventListener("progress", handleEvent);
            source.addEventListener("message", handleEvent);
            source.addEventListener("result", (event) => {
              window.clearTimeout(timeout);
              source.close();
              eventSourceRef.current = null;
              try {
                resolve(JSON.parse((event as MessageEvent).data));
              } catch {
                reject(new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại."));
              }
            });
            source.onerror = () => {
              window.clearTimeout(timeout);
              source.close();
              eventSourceRef.current = null;
              reject(new Error("SSE unavailable"));
            };
            abortController.signal.addEventListener("abort", () => {
              window.clearTimeout(timeout);
              source.close();
              eventSourceRef.current = null;
              reject(new DOMException("Aborted", "AbortError"));
            }, { once: true });
          });
        } catch (sseError) {
          if (abortController.signal.aborted) throw sseError;
          const result = await fetch(API_PATH, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: submitted }),
            signal: abortController.signal,
          });
          payload = await result.json().catch(() => null);
          if (!result.ok) {
            const detail =
              payload &&
              typeof payload === "object" &&
              "error" in payload &&
              typeof payload.error === "object" &&
              payload.error !== null &&
              "message" in payload.error &&
              typeof payload.error.message === "string"
                ? payload.error.message
                : "Không thể xử lý câu hỏi.";
            throw new Error(detail);
          }
        }
      } else {
        const result = await fetch(API_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: submitted }),
          signal: abortController.signal,
        });
        payload = await result.json().catch(() => null);
        if (!result.ok) {
          const detail =
            payload &&
            typeof payload === "object" &&
            "error" in payload &&
            typeof payload.error === "object" &&
            payload.error !== null &&
            "message" in payload.error &&
            typeof payload.error.message === "string"
              ? payload.error.message
              : "Không thể xử lý câu hỏi.";
          throw new Error(detail);
        }
      }
      const nextResponse = validateChatResponse(payload);
      setResponse(nextResponse);
      setTurns((previous) => [
        ...previous,
        { question: submitted, response: nextResponse },
      ]);
      setQuestion("");
    } catch (submissionError) {
      if (
        submissionError instanceof DOMException &&
        submissionError.name === "AbortError"
      )
        return;
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Không thể xử lý câu hỏi.",
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
  useEffect(() => () => {
    eventSourceRef.current?.close();
    abortControllerRef.current?.abort();
  }, []);
  const suggestions = [
    "Mức phạt khi vượt đèn đỏ là bao nhiêu?",
    "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?",
    "Có được dùng điện thoại khi đang lái xe không?",
  ];
  const resetConversation = () => {
    stopSubmission();
    setQuestion("");
    setResponse(null);
    setTurns([]);
    setSubmittedQuestion("");
    setError("");
  };
  return (
    <main className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        activeQuestion={submittedQuestion}
        onNewChat={resetConversation}
        onCollapsedChange={setSidebarCollapsed}
      />
      <section className="main-panel" aria-label="Khu vực tra cứu">
        <AppHeader />
        <div
          className={
            response || loading || error
              ? "conversation has-messages"
              : "conversation"
          }
          aria-busy={loading}
        >
          {!response && !loading && !error ? (
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
          {(response || loading || error) && (
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
      <SourceDrawer
        citation={drawerCitation}
        onClose={() => setDrawerCitation(null)}
      />
    </main>
  );
}
