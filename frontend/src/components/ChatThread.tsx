"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Clipboard, FileDown } from "lucide-react";
import AbstentionResult from "./AbstentionResult";
import CitationCard, { type Citation } from "./CitationCard";
import FeedbackWidget, { BookmarkToggle } from "./FeedbackWidget";
import PrintAnswerDocument from "./PrintAnswerDocument";
import type { ChatResponse, ConversationTurn, ProgressEvent } from "./chat-types";

function protectLegalParentheticals(markdown: string): string {
  return markdown.replace(
    /(?<!\\)\((?=[^()\n]*(?:khoản|điểm|điều|nghị định|thông tư)[^()\n]*\d)[^()\n]*\)/gi,
    "\\$&",
  );
}

const tableSeparator = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;

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
    const text = markdownLines.join("\n");
    if (text.trim()) parts.push({ kind: "markdown", text });
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
    <div className="markdown-answer">
      {splitAnswerTables(answer).map((part, index) =>
        part.kind === "markdown" ? (
          <ReactMarkdown key={index}>{protectLegalParentheticals(part.text)}</ReactMarkdown>
        ) : (
          <table key={index}>
            <thead>
              <tr>
                {part.headers.map((header) => (
                  <th key={header}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {part.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ),
      )}
    </div>
  );
}

type ChatThreadProps = {
  turns: ConversationTurn[];
  question: string;
  loading: boolean;
  error: string;
  historyLoading?: boolean;
  onOpenSource: (citation: Citation) => void;
  progressEvents?: ProgressEvent[];
  sessionId: string;
};

function ResponseMessage({
  question,
  response,
  onOpenSource,
  sessionId,
}: {
  question: string;
  response: ChatResponse;
  onOpenSource: (citation: Citation) => void;
  sessionId: string;
}) {
  const citations = response.citations ?? [];
  const verified = response.status === "VERIFIED";
  const operational =
    response.status === "INSUFFICIENT_EVIDENCE" ||
    response.status === "GREETING" ||
    response.status === "OUT_OF_SCOPE" ||
    response.status === "CORPUS_NOT_COVERED" ||
    response.status === "WORKFLOW_UNAVAILABLE";
  const [actionState, setActionState] = useState("");
  const [printing, setPrinting] = useState(false);
  const answer = response.answer ?? "";
  useEffect(() => {
    if (!printing) return;
    const finish = () => setPrinting(false);
    window.addEventListener("afterprint", finish, { once: true });
    const frame = window.requestAnimationFrame(() => window.print());
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("afterprint", finish);
    };
  }, [printing]);
  return (
    <div className="assistant-message response-message">
      <div className="response-content">
        {operational ? (
          <AbstentionResult
            status={
              response.status as
                | "GREETING"
                | "OUT_OF_SCOPE"
                | "CORPUS_NOT_COVERED"
                | "INSUFFICIENT_EVIDENCE"
                | "WORKFLOW_UNAVAILABLE"
            }
            reason={response.abstention?.reason}
            reasonCode={response.abstention?.reason_code}
            disclaimer={response.disclaimer}
          />
        ) : verified ? (
          <>
            <div className="answer-verification" role="status">
              <span aria-hidden="true">✓</span>
              <span>Đã đối chiếu nguồn</span>
              {citations.length > 0 && <span>{citations.length} căn cứ</span>}
            </div>
            <MarkdownAnswer answer={answer} />
            <div className="answer-actions" aria-label="Thao tác với câu trả lời">
              <div className="action-group">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(answer);
                    setActionState("Đã sao chép");
                  }}
                  aria-label="Sao chép"
                >
                  <Clipboard size={17} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => setPrinting(true)}
                  aria-label="In hoặc lưu câu trả lời thành PDF"
                  title="In hoặc lưu PDF"
                >
                  <FileDown size={17} aria-hidden="true" />
                </button>
                {actionState && <span role="status">{actionState}</span>}
                <FeedbackWidget
                  sessionId={sessionId}
                  messageId={response.assistant_message_id ?? ""}
                />
                <BookmarkToggle
                  sessionId={sessionId}
                  messageId={response.assistant_message_id ?? ""}
                  initialBookmarked={response.bookmarked ?? response.is_bookmarked ?? false}
                />
              </div>
            </div>
          </>
        ) : (
          <AbstentionResult
            status="INSUFFICIENT_EVIDENCE"
            reason={response.abstention?.reason}
            reasonCode={response.abstention?.reason_code}
            disclaimer={response.disclaimer}
          />
        )}
        {verified && citations.length > 0 && (
          <details className="citations">
            <summary>
              <span className="citations__label">
                Căn cứ pháp lý <strong>({citations.length})</strong>
              </span>
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
        {printing && (
          <PrintAnswerDocument question={question} answer={answer} citations={citations} />
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
  const endRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const thread = threadRef.current;
    const end = endRef.current;
    if (!thread || !end) return;
    const distance = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    if (distance < 160) end.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, historyLoading, error, question]);
  return (
    <div ref={threadRef} className="thread">
      {historyLoading && (
        <p className="history-loading" role="status" aria-live="polite">
          Đang tải cuộc trò chuyện…
        </p>
      )}
      {!historyLoading &&
        turns.map((turn, index) => (
          <div key={`${turn.question}-${index}`}>
            <div className="user-message">
              <div className="query-bubble" aria-label="Câu hỏi đã gửi">
                {turn.question}
              </div>
            </div>
            {turn.response && (
              <ResponseMessage
                question={turn.question}
                response={turn.response}
                onOpenSource={onOpenSource}
                sessionId={sessionId}
              />
            )}
            {!turn.response && turn.status === "failed" && (
              <p className="turn-status turn-status--failed" role="status">
                Không nhận được câu trả lời. Câu hỏi đã được đưa lại vào ô nhập để bạn thử lại.
              </p>
            )}
            {!turn.response && turn.status === "stopped" && (
              <p className="turn-status" role="status">
                Đã dừng tra cứu. Câu hỏi vẫn ở ô nhập để bạn chỉnh sửa hoặc gửi lại.
              </p>
            )}
          </div>
        ))}
      {!historyLoading && loading && (
        <div className="assistant-message loading-state" role="status" aria-live="polite">
          <div className="loading-content">
            <span className="streaming-badge">Đang tra cứu</span>
            <section className="progress-events-panel" aria-label="Tiến trình xử lý">
              <ol className="progress-events">
                {["Đang tìm căn cứ", "Đang đối chiếu nguồn", "Đang soạn câu trả lời"].map(
                  (label, index) => {
                    const activeIndex = Math.min(progressEvents?.length ?? 0, 2);
                    const state =
                      index < activeIndex
                        ? "complete"
                        : index === activeIndex
                          ? "active"
                          : "pending";
                    return (
                      <li
                        key={label}
                        className={`progress-events__item progress-events__item--${state}`}
                      >
                        <span className="progress-events__marker" aria-hidden="true">
                          {state === "complete" ? (
                            "✓"
                          ) : state === "active" ? (
                            <span className="progress-events__spinner" />
                          ) : (
                            index + 1
                          )}
                        </span>
                        <span className="progress-events__label">{label}</span>
                      </li>
                    );
                  },
                )}
              </ol>
            </section>
          </div>
        </div>
      )}
      {!historyLoading && error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
