import AbstentionResult from "./AbstentionResult";
import CitationCard, { type Citation } from "./CitationCard";
import FeedbackWidget from "./FeedbackWidget";
import LegalMark from "./LegalMark";
import ProgressEvents from "./ProgressEvents";
import type { ChatResponse, ConversationTurn } from "./chat-types";

type ChatThreadProps = {
  turns: ConversationTurn[];
  question: string;
  response: ChatResponse | null;
  loading: boolean;
  error: string;
  onOpenSource: (citation: Citation) => void;
};

function ResponseMessage({ response, onOpenSource }: { response: ChatResponse; onOpenSource: (citation: Citation) => void }) {
  const abstained = response.status === "ABSTAINED";
  return (
    <div className="assistant-message response-message">
      <LegalMark />
      <div className="response-content">
        <div className="message-meta"><strong>Trợ lý Luật Giao thông</strong><span>{abstained ? "Chưa đủ căn cứ" : "Đã đối chiếu nguồn pháp luật"}</span></div>
        {abstained ? <AbstentionResult reason={response.abstention?.reason} reasonCode={response.abstention?.reason_code} disclaimer={response.disclaimer} /> : <p className="assistant-answer">{response.answer}</p>}
        <ProgressEvents events={response.progress_events} />
        {!abstained && response.citations.length > 0 && (
          <section className="citations" aria-label="Căn cứ pháp lý">
            <h2>Căn cứ pháp lý</h2>
            <div className="citation-list">{response.citations.map((citation, index) => <CitationCard key={`${citation.provision_id}-${index}`} citation={citation} onOpenSource={onOpenSource} />)}</div>
          </section>
        )}
        {!abstained && response.trace_id && <FeedbackWidget traceId={response.trace_id} />}
      </div>
    </div>
  );
}

export default function ChatThread({ turns, question, loading, error, onOpenSource }: ChatThreadProps) {
  const loadingLabel = question ? `Đang xử lý: ${question}` : "Đang chuẩn bị tra cứu";
  return (
    <div className="thread">
      {turns.map((turn, index) => (
        <div key={`${turn.question}-${index}`}>
          <div className="user-message"><div className="query-bubble" aria-label="Câu hỏi đã gửi">{turn.question}</div></div>
          <ResponseMessage response={turn.response} onOpenSource={onOpenSource} />
        </div>
      ))}
      {loading && <div className="assistant-message loading-state" role="status" aria-live="polite"><LegalMark /><div><div className="message-meta"><strong>Trợ lý Luật Giao thông</strong><span>{loadingLabel}</span></div><span className="loading-bar" aria-hidden="true" /><p>Đang đối chiếu quy định và nguồn pháp luật...</p></div></div>}
      {error && <p role="alert" className="error-message">{error}</p>}
    </div>
  );
}
