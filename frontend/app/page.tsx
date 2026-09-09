"use client";

import { FormEvent, useEffect, useState } from "react";
import AppHeader from "../src/components/AppHeader";
import ChatThread from "../src/components/ChatThread";
import Composer from "../src/components/Composer";
import Sidebar from "../src/components/Sidebar";
import SourceDrawer from "../src/components/SourceDrawer";
import Welcome from "../src/components/Welcome";
import type { ChatResponse, Claim, ConversationTurn } from "../src/components/chat-types";
import type { Citation } from "../src/components/CitationCard";

const API_PATH = "/api/v1/chat";
const isCitation = (value: unknown): value is Citation => typeof value === "object" && value !== null && typeof (value as Citation).provision_id === "string";
const validateChatResponse = (payload: unknown): ChatResponse => {
  if (typeof payload !== "object" || payload === null) throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
  const value = payload as Record<string, unknown>;
  if (value.status === "ABSTAINED" && typeof value.abstention === "object" && value.abstention !== null) {
    const abstention = value.abstention as Record<string, unknown>;
    if ((typeof abstention.reason_code === "string" && Boolean(abstention.reason_code.trim())) || (typeof abstention.reason === "string" && Boolean(abstention.reason.trim()))) return payload as ChatResponse;
  }
  const claims = value.claims;
  const citations = value.citations;
  if (value.status === "VERIFIED" && typeof value.answer === "string" && Boolean(value.answer.trim()) && Array.isArray(claims) && claims.length > 0 && claims.every((claim): claim is Claim => typeof claim === "object" && claim !== null && typeof (claim as Claim).claim === "string" && Boolean((claim as Claim).claim.trim())) && Array.isArray(citations) && citations.length > 0 && citations.every(isCitation)) return payload as ChatResponse;
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
  const [theme, setTheme] = useState<"auto" | "light" | "dark">("auto");
  useEffect(() => { const stored = window.localStorage.getItem("vnlaw-theme"); const next = stored === "light" || stored === "dark" ? stored : "auto"; const apply = () => { document.documentElement.dataset.theme = next === "auto" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : next; }; apply(); const media = window.matchMedia("(prefers-color-scheme: dark)"); media.addEventListener("change", apply); return () => media.removeEventListener("change", apply); }, []);
  useEffect(() => { window.localStorage.setItem("vnlaw-theme", theme); document.documentElement.dataset.theme = theme === "auto" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme; }, [theme]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const submitted = question.trim(); if (!submitted || loading) return; setLoading(true); setError(""); setResponse(null); setSubmittedQuestion(submitted); try { const result = await fetch(API_PATH, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: submitted }) }); const payload: unknown = await result.json().catch(() => null); if (!result.ok) { const message = typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "object" && payload.error !== null && "message" in payload.error && typeof payload.error.message === "string" ? payload.error.message : "Không thể xử lý câu hỏi."; throw new Error(message); } const nextResponse = validateChatResponse(payload); setResponse(nextResponse); setTurns((previous) => [...previous, { question: submitted, response: nextResponse }]); setQuestion(""); } catch (submissionError) { setError(submissionError instanceof Error ? submissionError.message : "Không thể xử lý câu hỏi."); } finally { setLoading(false); } }
  const suggestions = ["Mức phạt khi vượt đèn đỏ là bao nhiêu?", "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?", "Có được dùng điện thoại khi đang lái xe không?"];
  const resetConversation = () => { setQuestion(""); setResponse(null); setTurns([]); setSubmittedQuestion(""); setError(""); };
  return <main className="app-shell"><Sidebar activeQuestion={submittedQuestion} suggestions={suggestions} onNewChat={resetConversation} onSuggestion={setQuestion} /><section className="main-panel" aria-label="Khu vực tra cứu"><AppHeader theme={theme} onTheme={setTheme} /><div className={response || loading || error ? "conversation has-messages" : "conversation"} aria-busy={loading}>{!response && !loading && !error ? <Welcome question={question} suggestions={suggestions} onQuestion={setQuestion} onSubmit={submit} /> : <ChatThread turns={turns} question={submittedQuestion} response={response} loading={loading} error={error} onOpenSource={setDrawerCitation} />}{(response || loading || error) && <div className="sticky-composer"><Composer id="question" value={question} onChange={setQuestion} onSubmit={submit} loading={loading} /></div>}</div></section><SourceDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} /></main>;
}
