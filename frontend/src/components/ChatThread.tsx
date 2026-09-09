"use client";
import { useEffect, useRef } from "react";
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
  error: string;
  onOpenSource: (citation: Citation) => void;
  progressEvents?: ProgressEvent[];
};

function ResponseMessage({
  response,
  onOpenSource,
}: {
  response: ChatResponse;
  onOpenSource: (citation: Citation) => void;
}) {
  const abstained = response.status === "ABSTAINED";
  return (
    <div className="assistant-message response-message">
      <LegalMark />
      <div className="response-content">
        <div className="message-meta">
          <strong>Trợ lý Luật Giao thông</strong>
          <span>
            {abstained ? "Chưa đủ căn cứ" : "Đã đối chiếu nguồn pháp luật"}
          </span>
        </div>
        {abstained ? (
          <AbstentionResult
            reason={response.abstention?.reason}
            reasonCode={response.abstention?.reason_code}
            disclaimer={response.disclaimer}
          />
        ) : (
          <p className="assistant-answer">{response.answer}</p>
        )}
        {!abstained && response.citations.length > 0 && (
          <section className="citations" aria-label="Căn cứ pháp lý">
            <h2>Căn cứ pháp lý</h2>
            <div className="citation-list">
              {response.citations.map((citation, index) => (
                <CitationCard
                  key={`${citation.provision_id}-${index}`}
                  citation={citation}
                  onOpenSource={onOpenSource}
                />
              ))}
            </div>
          </section>
        )}
        {!abstained && response.trace_id && (
          <FeedbackWidget traceId={response.trace_id} />
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
  onOpenSource,
  progressEvents,
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
  }, [turns.length, loading, error, question, reducedMotion]);
  const entrance = reducedMotion ? undefined : messageEntrance;
  return (
    <div ref={threadRef} className="thread">
      {turns.map((turn, index) => (
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
          />
        </motion.div>
      ))}
      {loading && (
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
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div ref={endRef} aria-hidden="true" />
    </div>
  );
}