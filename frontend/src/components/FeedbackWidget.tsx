"use client";

import { useRef, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
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
    if (value || state === "submitting") return;
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
      setState("error");
      setError(
        submissionError instanceof Error ? submissionError.message : "Không thể gửi phản hồi.",
      );
    }
  }

  return (
    <div className="feedback-widget" aria-busy={state === "submitting"}>
      <div className="feedback-widget__choice" role="group" aria-label="Đánh giá">
        <button
          className="feedback-widget__choice-button"
          type="button"
          aria-label="Thích"
          title="Thích"
          aria-pressed={value === "LIKE"}
          disabled={Boolean(value) || state === "submitting"}
          onClick={() => void submit("LIKE")}
        >
          <ThumbsUp size={17} aria-hidden="true" />
        </button>
        <button
          className="feedback-widget__choice-button"
          type="button"
          aria-label="Không thích"
          title="Không thích"
          aria-pressed={value === "DISLIKE"}
          disabled={Boolean(value) || state === "submitting"}
          onClick={() => void submit("DISLIKE")}
        >
          <ThumbsDown size={17} aria-hidden="true" />
        </button>
      </div>
      {state === "error" && (
        <span className="feedback-widget__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
