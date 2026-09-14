"use client";

import { useRef, useState } from "react";
import { Bookmark, LoaderCircle, ThumbsDown, ThumbsUp } from "lucide-react";
import { createClient } from "../../utils/supabase/client";
import { apiUrl } from "../lib/api";

type FeedbackValue = "LIKE" | "DISLIKE";
type SubmissionState = "idle" | "submitting" | "success" | "error";

export type FeedbackWidgetProps = {
  sessionId: string;
  messageId: string;
  endpoint?: string;
};

export default function FeedbackWidget({
  sessionId,
  messageId,
  endpoint = `chats/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/feedback`,
}: FeedbackWidgetProps) {
  const supabase = useRef(createClient()).current;
  const [value, setValue] = useState<FeedbackValue | null>(null);
  const [state, setState] = useState<SubmissionState>("idle");
  const [error, setError] = useState("");
  const apiEndpoint = apiUrl(endpoint);

  async function submit(nextValue: FeedbackValue) {
    if (value || state === "submitting" || state === "success") return;
    setValue(nextValue);
    setState("submitting");
    try {
      const { data } = await supabase.auth.getSession();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
      const response = await fetch(apiEndpoint, {
        method: "POST",
        headers,
        body: JSON.stringify({
          rating: nextValue === "LIKE" ? 1 : 0,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        throw new Error(payload?.error?.message || "Không thể gửi phản hồi.");
      }
      setState("success");
    } catch (submissionError) {
      setValue(null);
      setState("error");
      setError(
        submissionError instanceof Error ? submissionError.message : "Không thể gửi phản hồi.",
      );
    }
  }

  const isSubmitting = state === "submitting";
  const isLocked = state === "success";

  return (
    <div className="feedback-widget" aria-busy={isSubmitting}>
      <div className="feedback-widget__choice" role="group" aria-label="Đánh giá">
        <button
          className="feedback-widget__choice-button"
          type="button"
          aria-label="Thích"
          title="Thích"
          aria-pressed={value === "LIKE"}
          disabled={isLocked || isSubmitting}
          onClick={() => void submit("LIKE")}
        >
          {isSubmitting && value === "LIKE" ? (
            <LoaderCircle size={17} aria-hidden="true" className="animate-spin" />
          ) : (
            <ThumbsUp size={17} aria-hidden="true" />
          )}
        </button>
        <button
          className="feedback-widget__choice-button"
          type="button"
          aria-label="Không thích"
          title="Không thích"
          aria-pressed={value === "DISLIKE"}
          disabled={isLocked || isSubmitting}
          onClick={() => void submit("DISLIKE")}
        >
          {isSubmitting && value === "DISLIKE" ? (
            <LoaderCircle size={17} aria-hidden="true" className="animate-spin" />
          ) : (
            <ThumbsDown size={17} aria-hidden="true" />
          )}
        </button>
      </div>
      <span className="sr-only" role="status" aria-live="polite">
        {isSubmitting ? "Đang gửi phản hồi…" : isLocked ? "Đã gửi phản hồi." : ""}
      </span>
      {state === "error" && (
        <span className="feedback-widget__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export type BookmarkToggleProps = {
  sessionId: string;
  messageId: string;
  initialBookmarked?: boolean;
  endpoint?: string;
};

export function BookmarkToggle({
  sessionId,
  messageId,
  initialBookmarked = false,
  endpoint,
}: BookmarkToggleProps) {
  const supabase = useRef(createClient()).current;
  const [bookmarked, setBookmarked] = useState(initialBookmarked);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = endpoint ? apiUrl(endpoint) : apiUrl(`bookmarks/${encodeURIComponent(sessionId)}`);

  async function toggle() {
    if (submitting) return;
    const previous = bookmarked;
    const next = !previous;
    setBookmarked(next);
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await supabase.auth.getSession();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ message_id: messageId }),
      });
      const payload = (await response.json().catch(() => null)) as {
        bookmarked?: boolean;
        is_bookmarked?: boolean;
        saved?: boolean;
      } | null;
      if (!response.ok) throw new Error("Không thể cập nhật mục đã lưu.");
      const serverState = payload?.bookmarked ?? payload?.is_bookmarked ?? payload?.saved;
      setBookmarked(typeof serverState === "boolean" ? serverState : next);
    } catch (toggleError) {
      setBookmarked(previous);
      setError(
        toggleError instanceof Error ? toggleError.message : "Không thể cập nhật mục đã lưu.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <span className="bookmark-toggle">
      <button
        type="button"
        className="feedback-widget__choice-button"
        aria-label={bookmarked ? "Bỏ lưu câu trả lời" : "Lưu câu trả lời"}
        title={bookmarked ? "Bỏ lưu" : "Lưu"}
        aria-pressed={bookmarked}
        aria-busy={submitting}
        disabled={submitting}
        onClick={() => void toggle()}
      >
        {submitting ? (
          <LoaderCircle size={17} aria-hidden="true" className="animate-spin" />
        ) : (
          <Bookmark size={17} aria-hidden="true" fill={bookmarked ? "currentColor" : "none"} />
        )}
      </button>
      {error && (
        <span className="feedback-widget__error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
