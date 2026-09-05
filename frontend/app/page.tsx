"use client";

import { FormEvent, useState } from "react";

import FeedbackWidget from "../src/components/FeedbackWidget";
import CitationCard from "../src/components/CitationCard";
import QueryControls from "../src/components/QueryControls";
import SourceDrawer from "../src/components/SourceDrawer";
import AbstentionResult from "../src/components/AbstentionResult";
import ProgressEvents from "../src/components/ProgressEvents";

type Claim = {
  claim?: string;
  claim_type?: string;
  provision_ids?: string[];
};

type Citation = {
  provision_id?: string;
  document_number?: string;
  article?: string;
  source_url?: string;
  source_text?: string;
  page?: number | string;
  bbox?: number[];
};

type ChatResponse = {
  status?: "VERIFIED" | "ABSTAINED";
  answer?: string | null;
  claims?: Claim[];
  citations?: Citation[];
  abstention?: { reason_code?: string } | null;
  disclaimer?: string;
  progress_events?: Array<Record<string, unknown>>;
  trace_id?: string;
};

const API_PATH = "/api/v1/chat";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [queryDate, setQueryDate] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [comparisonDate, setComparisonDate] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    setResponse(null);
    try {
      const body: { question: string; query_date?: string; vehicle?: string } = {
        question: question.trim(),
      };
      if (queryDate) body.query_date = queryDate;
      if (vehicle.trim()) body.vehicle = vehicle.trim();
      const result = await fetch(API_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await result.json().catch(() => null);
      if (!result.ok) {
        throw new Error(payload?.error?.message || "Không thể gửi câu hỏi. Vui lòng thử lại.");
      }
      setResponse(payload as ChatResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Đã xảy ra lỗi không xác định.");
    } finally {
      setLoading(false);
    }
  }

  const abstained = response?.status === "ABSTAINED";

  return (
    <main className="chat-page">
      <section className="chat-shell" aria-labelledby="page-title">
        <header>
          <p className="eyebrow">VNLaw RAG</p>
          <h1 id="page-title">Hỏi đáp pháp luật giao thông</h1>
          <p className="intro">Đặt câu hỏi để nhận câu trả lời có kiểm chứng và căn cứ pháp lý rõ ràng.</p>
        </header>

        <form className="question-form" onSubmit={submit}>
          <label htmlFor="question">Câu hỏi</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ví dụ: Mức phạt khi vượt đèn đỏ là bao nhiêu?"
            rows={4}
            required
            maxLength={10000}
            aria-describedby="question-help"
          />
          <p id="question-help" className="field-help">Nêu tình huống cụ thể để kết quả chính xác hơn.</p>
          <QueryControls queryDate={queryDate} vehicle={vehicle} comparisonDate={comparisonDate} onQueryDateChange={setQueryDate} onVehicleChange={setVehicle} onComparisonDateChange={setComparisonDate} />
          <button type="submit" disabled={loading || !question.trim()} aria-busy={loading}>
            {loading ? "Đang kiểm tra..." : "Gửi câu hỏi"}
          </button>
        </form>

        {error && (
          <div className="alert error" role="alert">
            <strong>Không thể tải câu trả lời</strong>
            <p>{error}</p>
          </div>
        )}

        {response && (
          <section className="answer" aria-live="polite" aria-labelledby="answer-title">
            <div className={`status ${abstained ? "status-warning" : "status-success"}`}>
              {abstained ? "Chưa đủ căn cứ" : "Đã kiểm chứng"}
            </div>
            <h2 id="answer-title">Kết quả</h2>
            {abstained ? (
              <AbstentionResult reason={response.abstention?.reason_code} reasonCode={response.abstention?.reason_code} disclaimer={response.disclaimer} />
            ) : (
              <>
                <p className="answer-text">{response.answer || "Không có nội dung trả lời."}</p>
                {!!response.claims?.length && (
                  <div>
                    <h3>Các nhận định</h3>
                    <ul className="claims">
                      {response.claims.map((claim, index) => (
                        <li key={`${claim.claim}-${index}`}>
                          <span>{claim.claim}</span>
                          {claim.claim_type && <small>{claim.claim_type}</small>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
            {!!response.citations?.length && (
              <div>
                <h3>Căn cứ pháp lý</h3>
                <ul className="citations">
                  {response.citations.map((citation, index) => (
                    <li key={`${citation.provision_id}-${index}`}>
                      <CitationCard citation={citation} onOpenSource={setDrawerCitation} />
                      {citation.article && <span> · {citation.article}</span>}
                      {citation.source_url && (
                        <a href={citation.source_url} target="_blank" rel="noreferrer">Xem nguồn</a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {response.progress_events && <ProgressEvents events={response.progress_events} />}
            {response.disclaimer && <p className="disclaimer">{response.disclaimer}</p>}
            {response.trace_id && <details className="trace"><summary>Thông tin truy vết</summary><code>{response.trace_id}</code></details>}
            {response.trace_id && <FeedbackWidget traceId={response.trace_id} />}
            <SourceDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} />
          </section>
        )}
      </section>
      <style>{styles}</style>
    </main>
  );
}

const styles = `
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f4f7fb; color: #172033; font-family: Arial, sans-serif; }
  .chat-page { min-height: 100vh; padding: 40px 16px 72px; }
  .chat-shell { max-width: 820px; margin: auto; }
  header { margin-bottom: 28px; }
  .eyebrow { color: #185abd; font-size: .8rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
  h1 { margin: 8px 0 12px; font-size: clamp(1.8rem, 5vw, 2.8rem); }
  h2, h3 { margin-top: 0; }
  h3 { margin-bottom: 12px; font-size: 1rem; }
  .intro { color: #536174; max-width: 620px; }
  .question-form, .answer { border: 1px solid #dbe3ef; border-radius: 14px; background: white; padding: 24px; box-shadow: 0 5px 18px #26364d12; }
  label { display: block; margin: 0 0 8px; font-weight: 700; }
  textarea, input { width: 100%; border: 1px solid #aebbd0; border-radius: 8px; color: inherit; font: inherit; padding: 11px 12px; }
  textarea:focus, input:focus, button:focus-visible, a:focus-visible, summary:focus-visible { outline: 3px solid #9cc4ff; outline-offset: 2px; border-color: #185abd; }
  textarea { resize: vertical; }
  .field-help { color: #607087; font-size: .875rem; margin: 7px 0 20px; }
  .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 22px; }
  button { border: 0; border-radius: 8px; background: #185abd; color: white; cursor: pointer; font: inherit; font-weight: 700; padding: 12px 18px; }
  button:hover:not(:disabled) { background: #0e438c; }
  button:disabled { cursor: wait; opacity: .6; }
  .answer { margin-top: 24px; }
  .status { display: inline-block; border-radius: 999px; font-size: .82rem; font-weight: 700; margin-bottom: 14px; padding: 6px 10px; }
  .status-success { background: #e4f5e9; color: #146b34; }
  .status-warning { background: #fff1d6; color: #8a5200; }
  .answer-text { font-size: 1.1rem; line-height: 1.65; white-space: pre-wrap; }
  .claims, .citations { list-style: none; margin: 0 0 24px; padding: 0; }
  .claims li, .citations li { border-left: 3px solid #b9d2f6; margin-bottom: 10px; padding: 9px 12px; }
  .claims small { color: #607087; display: block; margin-top: 5px; }
  .citations a { margin-left: 8px; color: #185abd; }
  .alert { border-radius: 8px; padding: 14px 16px; }
  .alert p { margin: 5px 0; }
  .error { background: #fff0f0; border: 1px solid #efb4b4; color: #8b1e1e; margin-top: 20px; }
  .warning { background: #fff8e9; border: 1px solid #f0d391; color: #684800; }
  .disclaimer { border-top: 1px solid #e2e8f0; color: #536174; font-size: .875rem; margin: 24px 0 14px; padding-top: 16px; }
  .trace { color: #536174; font-size: .8rem; }
  .trace code { display: block; margin-top: 8px; overflow-wrap: anywhere; }
  @media (max-width: 560px) { .chat-page { padding-top: 24px; } .question-form, .answer { padding: 18px; } .form-grid { grid-template-columns: 1fr; } }
`;
