"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { motion, useReducedMotion } from "motion/react";
import { Clipboard, FileDown, Share2 } from "lucide-react";
import AbstentionResult from "./AbstentionResult";
import CitationCard, { type Citation } from "./CitationCard";
import FeedbackWidget, { BookmarkToggle } from "./FeedbackWidget";
import LegalMark from "./LegalMark";
import type { Transition } from "motion/react";
import type { ChatResponse, ConversationTurn, ProgressEvent } from "./chat-types";

const motionTransition: Transition = { duration: 0.2, ease: "easeOut" };

const messageEntrance = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
};

function protectLegalParentheticals(markdown: string): string {
  return markdown.replace(
    /(?<!\\)\((?=[^()\n]*(?:khoản|điểm|điều|nghị định|thông tư)[^()\n]*\d)[^()\n]*\)/gi,
    "\\$&",
  );
}

const tableSeparator = /^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$/;

function splitAnswerTables(
  markdown: string,
): Array<
  { kind: "markdown"; text: string } | { kind: "table"; headers: string[]; rows: string[][] }
> {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const parts: Array<
    { kind: "markdown"; text: string } | { kind: "table"; headers: string[]; rows: string[][] }
  > = [];
  let markdownLines: string[] = [];
  const flushMarkdown = () => {
    if (markdownLines.join("\n").trim())
      parts.push({ kind: "markdown", text: markdownLines.join("\n") });
    markdownLines = [];
  };
  const lineCells = (line: string) =>
    line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim());
  for (let index = 0; index < lines.length; index += 1) {
    if (
      index + 1 >= lines.length ||
      !lines[index].includes("|") ||
      !tableSeparator.test(lines[index + 1])
    ) {
      markdownLines.push(lines[index]);
      continue;
    }
    const headers = lineCells(lines[index]);
    const separator = lineCells(lines[index + 1]);
    if (headers.length < 2 || separator.length !== headers.length) {
      markdownLines.push(lines[index]);
      continue;
    }
    flushMarkdown();
    const rows: string[][] = [];
    index += 2;
    while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
      const row = lineCells(lines[index]);
      if (row.length !== headers.length) break;
      rows.push(row);
      index += 1;
    }
    index -= 1;
    parts.push({ kind: "table", headers, rows });
  }
  flushMarkdown();
  return parts;
}

export function MarkdownAnswer({ answer }: { answer: string }) {
  return (
    <>
      {splitAnswerTables(protectLegalParentheticals(answer)).map((part, index) =>
        part.kind === "markdown" ? (
          <ReactMarkdown key={index} skipHtml>
            {part.text}
          </ReactMarkdown>
        ) : (
          <div className="assistant-answer-table" key={index}>
            <table>
              <thead>
                <tr>
                  {part.headers.map((header, cellIndex) => (
                    <th key={cellIndex} scope="col">
                      <ReactMarkdown skipHtml>{header}</ReactMarkdown>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {part.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>
                        <ReactMarkdown skipHtml>{cell}</ReactMarkdown>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      )}
    </>
  );
}

type ChatThreadProps = {
  turns: ConversationTurn[];
  question: string;
  loading: boolean;
  error?: string;
  historyLoading?: boolean;
  onOpenSource: (citation: Citation) => void;
  progressEvents?: ProgressEvent[];
  sessionId?: string;
};

function ResponseMessage({
  response,
  onOpenSource,
  sessionId,
}: {
  response: ChatResponse;
  onOpenSource: (citation: Citation) => void;
  sessionId?: string;
}) {
  const verified = response.status === "VERIFIED";
  const operational = response.status === "WORKFLOW_UNAVAILABLE";
  const citations = response.citations ?? [];
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
        ) : verified ? (
          <>
            <div className="assistant-answer">
              <MarkdownAnswer answer={answer} />
            </div>
            <div className="answer-actions" aria-label="Thao tác với câu trả lời">
              <button type="button" onClick={copyAnswer} aria-label="Sao chép" title="Sao chép">
                <Clipboard size={17} aria-hidden="true" />
              </button>
              {sessionId && response.assistant_message_id && (
                <>
                  <BookmarkToggle
                    sessionId={sessionId}
                    messageId={response.assistant_message_id}
                    initialBookmarked={response.bookmarked ?? response.is_bookmarked ?? false}
                  />
                  <FeedbackWidget sessionId={sessionId} messageId={response.assistant_message_id} />
                </>
              )}
              <button
                type="button"
                onClick={() => window.print()}
                aria-label="Xuất PDF"
                title="Xuất PDF"
              >
                <FileDown size={17} aria-hidden="true" />
              </button>
              <button type="button" onClick={shareAnswer} aria-label="Chia sẻ" title="Chia sẻ">
                <Share2 size={17} aria-hidden="true" />
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
  }, [turns.length, historyLoading, error, question, reducedMotion]);
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
                <section
                  className="progress-events-panel"
                  aria-label="Tiến trình xử lý"
                  aria-live="polite"
                >
                  <div className="progress-events__skeleton" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                  <p className="progress-events__event" role="status">
                    {progressEvents
                      ?.map((event) => event.message || event.detail)
                      .filter((message): message is string => Boolean(message))
                      .at(-1) || "Đang xử lý yêu cầu…"}
                  </p>
                </section>
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
