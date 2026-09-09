"use client";

import { FormEvent, useEffect, useState } from "react";
import AbstentionResult from "../src/components/AbstentionResult";
import CitationCard, { Citation } from "../src/components/CitationCard";
import FeedbackWidget from "../src/components/FeedbackWidget";
import ProgressEvents from "../src/components/ProgressEvents";
import SourceDrawer from "../src/components/SourceDrawer";

type Claim = { claim?: string; claim_type?: string; provision_ids?: string[] };
type ChatResponse = {
  status?: "VERIFIED" | "ABSTAINED";
  answer?: string | null;
  claims?: Claim[];
  citations?: Citation[];
  abstention?: { reason_code?: string; reason?: string } | null;
  disclaimer?: string;
  progress_events?: Array<Record<string, unknown>>;
  trace_id?: string;
};

const API_PATH = "/api/v1/chat";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<"auto" | "light" | "dark">("auto");
  useEffect(() => {
    const stored = window.localStorage.getItem("vnlaw-theme");
    const next = stored === "light" || stored === "dark" ? stored : "auto";
    const apply = () => { document.documentElement.dataset.theme = next === "auto" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : next; };
    apply();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);
  useEffect(() => {
    window.localStorage.setItem("vnlaw-theme", theme);
    document.documentElement.dataset.theme = theme === "auto" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
  }, [theme]);
  useEffect(() => { const hide = () => document.getElementById("__next-route-announcer__")?.setAttribute("aria-hidden", "true"); hide(); const observer = new MutationObserver(hide); observer.observe(document.body, { childList: true, subtree: true }); return () => observer.disconnect(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || loading) return;
    setLoading(true);
    setError("");
    setResponse(null);
    setSubmittedQuestion(submittedQuestion);
    try {
      const result = await fetch(API_PATH, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: submittedQuestion }) });
      const payload: unknown = await result.json().catch(() => null);
      if (!result.ok) {
        const message = typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "object" && payload.error !== null && "message" in payload.error && typeof payload.error.message === "string" ? payload.error.message : "Không thể gửi câu hỏi. Vui lòng thử lại.";
        throw new Error(message);
      }
      if (!payload || typeof payload !== "object") throw new Error("Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.");
      setResponse(payload as ChatResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không thể gửi câu hỏi. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  const abstained = response?.status === "ABSTAINED";
  const suggestions = ["Mức phạt khi vượt đèn đỏ là bao nhiêu?", "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?", "Có được dùng điện thoại khi đang lái xe không?"];
  const resetConversation = () => { setQuestion(""); setResponse(null); setError(""); };

  return (
    <main className="chat-page">
      <div className="chat-shell">
        <aside className="context-panel" aria-label="Thông tin ứng dụng">
          <div className="brand-lockup"><div className="brand-mark" aria-hidden="true">VN</div><div><strong>VNLAW</strong><span>Tra cứu pháp luật</span></div></div>
          <div className="panel-rule" />
          <p className="panel-kicker">NGHIÊN CỨU GIAO THÔNG</p>
          <h2>Tra cứu để hiểu đúng luật.</h2>
          <p className="panel-note">Câu trả lời được tổng hợp từ các văn bản pháp luật Việt Nam và luôn kèm căn cứ để bạn kiểm tra.</p>
          <button type="button" className="new-conversation" onClick={resetConversation}><span aria-hidden="true">+</span> Cuộc trò chuyện mới</button>
          <div className="panel-footer"><span className="footer-label">PHẠM VI</span><span>Luật giao thông đường bộ</span><span>Văn bản được kiểm chứng</span></div>
        </aside>
        <section className="chat-workspace" aria-label="Khu vực tra cứu">
          <header className="top-bar"><div><span className="eyebrow">TRỢ LÝ PHÁP LUẬT / 01</span><h1>Hỏi đáp pháp luật giao thông</h1></div><div className="top-bar-actions"><fieldset className="theme-picker"><legend>Giao diện</legend>{([['auto','Tự động'],['light','Sáng'],['dark','Tối']] as const).map(([value, label]) => <label key={value}><input type="radio" name="theme" value={value} checked={theme === value} onChange={() => setTheme(value)} /><span>{label}</span></label>)}</fieldset><span className="connection-status"><i aria-hidden="true" /> Sẵn sàng</span></div></header>
          <div className="conversation" aria-busy={loading}>
            {!response && !loading && <div className="empty-state"><div className="empty-index" aria-hidden="true">01</div><h2>Bạn cần tra cứu điều gì?</h2><p>Đặt câu hỏi về luật giao thông để nhận câu trả lời rõ ràng, có kiểm chứng.</p><div className="suggestions" aria-label="Gợi ý tra cứu">{suggestions.map((item, index) => <button key={item} type="button" onClick={() => setQuestion(item)}><span className="suggestion-index">0{index + 1}</span><span>{item}</span><span className="suggestion-arrow" aria-hidden="true">→</span></button>)}</div></div>}
            {loading && <div className="loading-state" role="status" aria-live="polite"><div className="query-bubble" aria-label="Câu hỏi đã gửi">{submittedQuestion}</div><span className="loading-bar" aria-hidden="true" /><strong>Đang chuẩn bị tra cứu</strong><span>Đang đối chiếu nguồn và chuẩn bị câu trả lời...</span></div>}
            <form onSubmit={submit} className="query-form"><label htmlFor="question">Câu hỏi</label><div className="query-input-row"><textarea id="question" required value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ví dụ: Mức phạt khi vượt đèn đỏ là bao nhiêu?" rows={2} /><button type="submit" disabled={loading || !question.trim()}>{loading ? "Đang tra cứu..." : "Gửi câu hỏi"}<span aria-hidden="true">↑</span></button></div><span className="form-hint">Nhấn Gửi câu hỏi để bắt đầu tra cứu</span></form>
            {error && <p role="alert" aria-label="Lỗi truy vấn" className="error-message">{error}</p>}
            {response && <section className={abstained ? "response abstained" : "response"} aria-live="polite">{abstained ? <AbstentionResult reason={response.abstention?.reason} reasonCode={response.abstention?.reason_code} disclaimer={response.disclaimer} /> : <><div className="response-heading motion-stage"><div><span className="eyebrow">KẾT QUẢ NGHIÊN CỨU</span><h2>Trả lời có căn cứ pháp lý</h2></div><b>ĐÃ KIỂM CHỨNG</b></div><div className="answer-body motion-stage">{response.answer}</div><ProgressEvents events={response.progress_events} /><div className="citations motion-stage">{response.citations?.map((citation, index) => <CitationCard key={citation.provision_id ?? index} citation={{ ...citation, document_title: citation.document_title || citation.document_number, document_number: undefined }} onOpenSource={(citation) => setDrawerCitation(citation)} />)}</div>{response.trace_id && <FeedbackWidget traceId={response.trace_id} />}</>}</section>}
          </div>
        </section>
      </div>
      {drawerCitation && <SourceDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} />}
    </main>
  );
}
