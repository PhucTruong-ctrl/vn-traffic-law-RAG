"use client";

import { useRef, useState } from "react";
import { LoaderCircle, ThumbsDown, ThumbsUp } from "lucide-react";
import { createClient } from "../../utils/supabase/client";

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
  endpoint = "/api/v1/feedback",
}: FeedbackWidgetProps) {
  const supabase = useRef(createClient()).current;
  const [value, setValue] = useState<FeedbackValue | null>(null);
  const [state, setState] = useState<SubmissionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

  async function submit(nextValue: FeedbackValue) {
    if (value || state === "submitting" || state === "success") return;
    setValue(nextValue);
    setState("submitting");
    setError(null);
    const { data } = await supabase.auth.getSession();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
    try {
      const response = await fetch(`${apiUrl}${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
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
