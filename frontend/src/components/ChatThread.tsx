"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { motion, useReducedMotion } from "motion/react";
import AbstentionResult from "./AbstentionResult";
import CitationCard, { type Citation } from "./CitationCard";
import FeedbackWidget from "./FeedbackWidget";
import LegalMark from "./LegalMark";
import ProgressEvents, { type ProgressEvent } from "./ProgressEvents";
import { messageEntrance, motionTransition } from "./motion";
import type { ChatResponse, ConversationTurn } from "./chat-types";

type ChatThreadProps = {
  turns: ConversationTurn[];
  question: string;
  loading: boolean;
  error?: string;
  historyLoading?: boolean;
  onOpenSource: (citation: Citation) => void;
  onClarificationOption: (option: string) => void;
  progressEvents?: ProgressEvent[];
  sessionId?: string;
};

function ResponseMessage({
  response,
  onOpenSource,
  onClarificationOption,
  loading,
  sessionId,
}: {
  response: ChatResponse;
  onOpenSource: (citation: Citation) => void;
  onClarificationOption: (option: string) => void;
  loading: boolean;
  sessionId?: string;
}) {
  const verified = response.status === "VERIFIED";
  const clarification = response.status === "CLARIFICATION_REQUIRED";
  const operational = response.status === "WORKFLOW_UNAVAILABLE";
  const citations = response.citations ?? [];
  const comparison = response.comparison;
  const [actionState, setActionState] = useState("");
  const answer = response.answer ?? "";

  async function copyAnswer() {
    if (typeof navigator.clipboard?.writeText !== "function") return;
    try {
      await navigator.clipboard.writeText(answer);
      setActionState("Đã sao chép");
    } catch {
      setActionState("");
    }
  }
  async function shareAnswer() {
    try {
      if (typeof navigator.share === "function") {
        await navigator.share({ text: answer });
        setActionState("Đã chia sẻ");
      } else if (typeof navigator.clipboard?.writeText === "function") {
        await navigator.clipboard.writeText(answer);
        setActionState("Đã sao chép");
      }
    } catch {
      setActionState("");
    }
  }

  return (
    <div className="assistant-message response-message">
      <LegalMark />
      <div className="response-content">
        <div className="message-meta">
          <strong>Trợ lý Luật Giao thông</strong>
          <span>
            {verified
              ? "Đã đối chiếu nguồn pháp luật"
              : clarification
                ? "Cần bổ sung thông tin"
                : operational
                  ? "Dịch vụ tạm thời không khả dụng"
                  : "Chưa đủ căn cứ"}
          </span>
        </div>
        {operational ? (
          <section className="abstention-result alert error" role="alert">
            <h2>Không thể xử lý yêu cầu lúc này</h2>
            <p>{response.disclaimer ?? "Hệ thống gặp lỗi vận hành. Vui lòng thử lại sau."}</p>
          </section>
        ) : clarification ? (
          <section className="clarification-result" aria-labelledby="clarification-title">
            <div className="assistant-answer" id="clarification-title">
              <ReactMarkdown skipHtml>
                {response.answer ?? "Bạn đang hỏi về loại phương tiện nào?"}
              </ReactMarkdown>
            </div>
            <div className="clarification-options" role="group" aria-label="Chọn thông tin bổ sung">
              {(response.options ?? []).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onClarificationOption(option)}
                  disabled={loading}
                >
                  {option}
                </button>
              ))}
            </div>
          </section>
        ) : verified ? (
          <>
            <div className="assistant-answer">
              <ReactMarkdown skipHtml>{answer}</ReactMarkdown>
            </div>
            <div className="answer-actions" aria-label="Thao tác với câu trả lời">
              <button type="button" onClick={copyAnswer}>
                Sao chép
              </button>
              <button type="button" onClick={() => window.print()}>
                Xuất PDF
              </button>
              <button type="button" onClick={shareAnswer}>
                Chia sẻ
              </button>
              {actionState && <span role="status">{actionState}</span>}
            </div>
          </>
        ) : (
          <AbstentionResult
            reason={response.abstention?.reason}
            reasonCode={response.abstention?.reason_code}
            disclaimer={response.disclaimer}
          />
        )}
        {verified && citations.length > 0 && (
          <details className="citations">
            <summary>
              Căn cứ pháp lý <span>({citations.length})</span>
            </summary>
            <div className="citation-list">
              {citations.map((citation, index) => (
                <CitationCard
                  key={`${citation.document_id ?? citation.document_title ?? citation.provision_id ?? "citation"}-${index}`}
                  citation={citation}
                  onOpenSource={onOpenSource}
                />
              ))}
            </div>
          </details>
        )}
        {verified && comparison?.answer && (
          <section className="comparison-result" aria-label="So sánh nguồn">
            <h3>{comparison.label ?? "So sánh nguồn"}</h3>
            <div className="comparison-answer">
              <ReactMarkdown skipHtml>{comparison.answer}</ReactMarkdown>
            </div>
          </section>
        )}
        {verified && sessionId && response.assistant_message_id && (
          <FeedbackWidget sessionId={sessionId} messageId={response.assistant_message_id} />
        )}
      </div>
    </div>
  );
}
export default function ChatThread({
  turns,
  question,
  loading,
  error,
  historyLoading = false,
  onOpenSource,
  onClarificationOption,
  progressEvents,
  sessionId,
}: ChatThreadProps) {
  const reducedMotion = useReducedMotion();
  const endRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const thread = threadRef.current;
    const end = endRef.current;
    if (!thread || !end) return;
    const distance = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    if (distance < 160) end.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
  }, [turns.length, loading, historyLoading, error, question, reducedMotion]);
  const entrance = reducedMotion ? undefined : messageEntrance;
  return (
    <div ref={threadRef} className="thread">
      {historyLoading && (
        <p className="history-loading" role="status" aria-live="polite">
          Đang tải cuộc trò chuyện…
        </p>
      )}
      {!historyLoading &&
        turns.map((turn, index) => (
          <motion.div
            key={`${turn.question}-${index}`}
            initial={entrance?.initial}
            animate={entrance?.animate}
            transition={motionTransition}
          >
            <div className="user-message">
              <div className="query-bubble" aria-label="Câu hỏi đã gửi">
                {turn.question}
              </div>
            </div>
            <ResponseMessage
              response={turn.response}
              onOpenSource={onOpenSource}
              onClarificationOption={onClarificationOption}
              loading={loading}
              sessionId={sessionId}
            />
          </motion.div>
        ))}
      {historyLoading
        ? null
        : loading && (
            <motion.div
              className="assistant-message loading-state"
              role="status"
              aria-live="polite"
              initial={entrance?.initial}
              animate={entrance?.animate}
              transition={motionTransition}
            >
              <LegalMark />
              <div className="loading-content">
                <div className="message-meta">
                  <strong>Trợ lý Luật Giao thông</strong>
                  <span className="streaming-badge">Đang trả lời</span>
                </div>
                <span className="loading-question">{question}</span>
                <ProgressEvents loading={loading} events={progressEvents} />
                <span className="loading-bar" aria-hidden="true" />
                <div className="loading-skeleton" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </motion.div>
          )}
      {!historyLoading && error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div ref={endRef} aria-hidden="true" />
    </div>
  );
}
