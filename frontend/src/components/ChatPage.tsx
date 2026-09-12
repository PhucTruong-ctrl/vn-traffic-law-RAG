"use client";

import { Eye, EyeOff } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import type { Session } from "@supabase/supabase-js";
import { createClient } from "../../utils/supabase/client";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const API_PATH = `${API_BASE}/api/v1/chat`;
const isCitation = (value: unknown): value is Citation => {
  if (typeof value !== "object" || value === null) return false;
  const citation = value as Record<string, unknown>;
  return (
    (typeof citation.provision_id === "string" && Boolean(citation.provision_id.trim())) ||
    (typeof citation.document === "string" && Boolean(citation.document.trim())) ||
    (typeof citation.document_title === "string" && Boolean(citation.document_title.trim())) ||
    (typeof citation.document_id === "string" && Boolean(citation.document_id.trim()))
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
  const enrich = (response: ChatResponse): ChatResponse => ({
    ...response,
    ...(typeof message.id === "string" ? { assistant_message_id: message.id } : {}),
    ...(typeof message.session_id === "string" ? { conversation_id: message.session_id } : {}),
  });
  if (typeof candidate === "string") {
    const citations = Array.isArray(message.citations) ? message.citations.filter(isCitation) : [];
    const answer = candidate.trim();
    if (!answer) return null;
    return enrich({
      status: message.status === "insufficient_evidence" ? "INSUFFICIENT_EVIDENCE" : "VERIFIED",
      answer,
      citations,
      claims: citations.map((citation) => ({
        claim:
          (typeof citation.excerpt === "string" && citation.excerpt) ||
          (typeof citation.source_text === "string" && citation.source_text) ||
          (typeof citation.snippet === "string" && citation.snippet) ||
          answer,
      })),
    });
  }
  if (!candidate || typeof candidate !== "object") return null;
  const value = candidate as Record<string, unknown>;
  const answer = typeof value.answer === "string" ? value.answer.trim() : "";
  const citations = Array.isArray(value.citations)
    ? value.citations.filter(isCitation)
    : Array.isArray(message.citations)
      ? message.citations.filter(isCitation)
      : [];
  if (!answer) return null;
  if (value.status && typeof value.status === "string" && value.status !== "complete") {
    return enrich({ ...value, answer, citations } as ChatResponse);
  }
  return enrich({
    ...value,
    status: "VERIFIED",
    answer,
    citations,
    claims:
      Array.isArray(value.claims) && value.claims.length
        ? value.claims
        : citations.map((citation) => ({ claim: citation.excerpt || answer })),
  } as ChatResponse);
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
  for (let index = 0; index < messages.length; index += 1) {
    const item = messages[index];
    if (!item || typeof item !== "object") continue;
    const message = item as Record<string, unknown>;
    if (
      typeof message.question === "string" &&
      (message.response !== undefined || message.payload !== undefined)
    ) {
      const response = responseFromMessage(message);
      if (response) turns.push({ question: message.question, response });
      continue;
    }
    if (
      (message.role === "user" || message.type === "user") &&
      typeof message.content === "string"
    ) {
      const next = messages[index + 1];
      const nextMessage =
        next && typeof next === "object" ? (next as Record<string, unknown>) : null;
      if (nextMessage?.role === "assistant" || nextMessage?.type === "assistant") {
        const response = responseFromMessage({
          ...nextMessage,
          session_id: typeof nextMessage.session_id === "string" ? nextMessage.session_id : raw.id,
        });
        if (response) {
          turns.push({ question: message.content, response });
          index += 1;
          continue;
        }
      }
      turns.push({
        question: message.content,
        response: {
          status: "WORKFLOW_UNAVAILABLE",
          answer: "Câu hỏi này chưa có phản hồi được lưu.",
          disclaimer: "Phản hồi chưa được lưu hoàn chỉnh; vui lòng gửi lại câu hỏi.",
        },
      });
    }
  }
  return turns;
}
export default function ChatPage({
  conversationId: initialConversationId,
}: {
  conversationId?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const conversationId = initialConversationId;
  const [question, setQuestion] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [conversationActivity, setConversationActivity] = useState<{
    id: string;
    nonce: number;
  } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(Boolean(conversationId));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [activeId, setActiveId] = useState(conversationId);
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [authError, setAuthError] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const supabase = useMemo(() => createClient(), []);
  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token
      ? { Authorization: `Bearer ${data.session.access_token}` }
      : {};
  }, [supabase]);
  useEffect(() => {
    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session);
        setAuthReady(true);
      }
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!mounted) return;
      setSession(next);
      setAuthReady(true);
    });
    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, [supabase]);
  useEffect(() => {
    const controller = new AbortController();
    if (!conversationId || !session) {
      if (!conversationId) {
        void Promise.resolve().then(() => {
          if (!controller.signal.aborted) setHistoryLoading(false);
        });
      }
      return () => controller.abort();
    }
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) setHistoryLoading(true);
    });
    void authHeaders()
      .then((headers) =>
        fetch(`${API_BASE}/api/v1/chats/${encodeURIComponent(conversationId)}`, {
          headers,
          signal: controller.signal,
        }),
      )
      .then((result) => {
        if (!result?.ok) throw new Error("Không thể tải cuộc trò chuyện.");
        return result.json();
      })
      .then((payload) => {
        setActiveId(conversationId);
        setTurns(turnsFromConversation(payload));
        setQuestion("");
        setSubmittedQuestion("");
        setError("");
        setHistoryLoading(false);
      })
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(
            loadError instanceof Error ? loadError.message : "Không thể tải cuộc trò chuyện.",
          );
          setHistoryLoading(false);
        }
      });
    return () => controller.abort();
  }, [conversationId, session, authHeaders]);

  const navigateTo = useCallback(
    (id?: string) => {
      const target = id ? `/chat/${encodeURIComponent(id)}` : "/chat";
      if (pathname !== target) router.push(target);
    },
    [pathname, router],
  );

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    if (authMode === "register" && password !== confirmPassword) {
      setAuthError("Mật khẩu xác nhận không khớp.");
      return;
    }
    const result =
      authMode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    if (result.error) setAuthError(result.error.message);
    else if (authMode === "register" && !result.data.session)
      setAuthError("Vui lòng xác nhận email trước khi đăng nhập.");
  }

  async function submitQuestion(submitted: string) {
    if (!submitted || loading || historyLoading || !session) return;
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setProgressEvents([]);
    setLoading(true);
    try {
      const result = await fetch(API_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(await authHeaders()) },
        body: JSON.stringify({
          question: submitted,
          ...(activeId ? { session_id: activeId } : {}),
        }),
        signal: abortController.signal,
      });
      const payload = await result.json().catch(() => null);
      if (!result.ok)
        throw new Error(payload?.detail || payload?.error?.message || "Không thể xử lý câu hỏi.");
      const nextResponse = validateChatResponse(payload);
      const responseId =
        typeof payload?.session_id === "string"
          ? payload.session_id
          : typeof payload?.conversation_id === "string"
            ? payload.conversation_id
            : typeof payload?.chat_id === "string"
              ? payload.chat_id
              : activeId;
      if (responseId && responseId !== activeId) {
        setActiveId(responseId);
        navigateTo(responseId);
      }
      setTurns((previous) => [...previous, { question: submitted, response: nextResponse }]);
      if (responseId) setConversationActivity({ id: responseId, nonce: Date.now() });
      setQuestion("");
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitQuestion(question.trim());
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
  if (!authReady)
    return (
      <main className="app-shell">
        <p role="status">Đang kiểm tra phiên đăng nhập…</p>
      </main>
    );
  if (!session)
    return (
      <main className="app-shell">
        <section className="main-panel auth-gate">
          <AppHeader />
          <form onSubmit={authenticate}>
            <h1>Đăng nhập để tra cứu</h1>
            <p>Vui lòng đăng nhập hoặc tạo tài khoản để sử dụng chat.</p>
            <label htmlFor="auth-email">
              Email
              <input
                id="auth-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label htmlFor="auth-password">
              Mật khẩu
              <span className="auth-password-field">
                <input
                  id="auth-password"
                  type={showPassword ? "text" : "password"}
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  type="button"
                  className="auth-password-toggle"
                  aria-label={showPassword ? "Hiện mật khẩu" : "Ẩn mật khẩu"}
                  aria-pressed={showPassword}
                  title={showPassword ? "Hiện mật khẩu" : "Ẩn mật khẩu"}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </span>
            </label>
            {authMode === "register" && (
              <label htmlFor="auth-confirm-password">
                Xác nhận mật khẩu
                <span className="auth-password-field">
                  <input
                    id="auth-confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    minLength={8}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="auth-password-toggle"
                    aria-label={
                      showConfirmPassword ? "Ẩn mật khẩu xác nhận" : "Hiện mật khẩu xác nhận"
                    }
                    aria-pressed={showConfirmPassword}
                    title={showConfirmPassword ? "Ẩn mật khẩu xác nhận" : "Hiện mật khẩu xác nhận"}
                    onClick={() => setShowConfirmPassword((visible) => !visible)}
                  >
                    {showConfirmPassword ? (
                      <EyeOff aria-hidden="true" />
                    ) : (
                      <Eye aria-hidden="true" />
                    )}
                  </button>
                </span>
              </label>
            )}
            {authError && <p role="alert">{authError}</p>}
            <button type="submit">{authMode === "login" ? "Đăng nhập" : "Đăng ký"}</button>
            <button
              type="button"
              onClick={() => {
                setAuthMode(authMode === "login" ? "register" : "login");
                setAuthError("");
              }}
            >
              {authMode === "login" ? "Tạo tài khoản" : "Đã có tài khoản"}
            </button>
          </form>
        </section>
      </main>
    );
  return (
    <main className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        activeConversationId={activeId}
        activeQuestion={submittedQuestion || turns.at(-1)?.question || ""}
        onNewChat={resetConversation}
        onSelectConversation={(id) => navigateTo(id)}
        onCollapsedChange={setSidebarCollapsed}
        onConversationActivity={conversationActivity}
      />
      <section className="main-panel" aria-label="Khu vực tra cứu">
        <AppHeader />
        <div
          className={
            turns.length || loading || historyLoading || error
              ? "conversation has-messages"
              : "conversation"
          }
          aria-busy={loading || historyLoading}
        >
          {!conversationId && !turns.length && !loading && !historyLoading && !error ? (
            <Welcome
              question={question}
              suggestions={suggestions}
              onQuestion={setQuestion}
              onSubmit={submit}
            />
          ) : (
            <ChatThread
              turns={turns}
              question={historyLoading ? "" : submittedQuestion}
              loading={loading}
              historyLoading={historyLoading}

              error={error}
              progressEvents={progressEvents}
              sessionId={activeId}
              onOpenSource={setDrawerCitation}
            />
          )}
          {(conversationId || turns.length > 0 || loading || historyLoading || error) && (
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
