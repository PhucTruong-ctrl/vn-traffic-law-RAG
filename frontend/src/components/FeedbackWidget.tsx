"use client";

import { FormEvent, useRef, useState } from "react";
import { createClient } from "../../utils/supabase/client";

type FeedbackValue = "LIKE" | "DISLIKE";
type SubmissionState = "idle" | "submitting" | "success" | "error";

export type FeedbackWidgetProps = {
  traceId: string;
  messageId?: string;
  endpoint?: string;
};

export default function FeedbackWidget({
  traceId,
  messageId,
  endpoint = "/api/v1/chats/feedback",
}: FeedbackWidgetProps) {
  const supabase = useRef(createClient()).current;
  const [value, setValue] = useState<FeedbackValue | null>(null);
  const [state, setState] = useState<SubmissionState>("idle");
  const [error, setError] = useState<string | null>(null);

  const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!value || !traceId || state === "submitting") return;
    setState("submitting");
    const { data } = await supabase.auth.getSession();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Trace-ID": traceId,
    };
    if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
    try {
      const response = await fetch(`${apiUrl}${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ trace_id: traceId, message_id: messageId, rating: value }),
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
    <section
      className="feedback-widget motion-entrance"
      aria-labelledby="feedback-heading"
      aria-busy={state === "submitting"}
    >
      <div className="feedback-widget__header">
        <span className="feedback-widget__eyebrow">ĐÁNH GIÁ</span>
        <h2 id="feedback-heading">Phản hồi câu trả lời</h2>
      </div>
      {state === "success" ? (
        <p className="feedback-widget__success" role="status">
          Cảm ơn bạn đã gửi phản hồi.
        </p>
      ) : (
        <form className="feedback-widget__form" onSubmit={submit}>
          <fieldset className="feedback-widget__fieldset" disabled={state === "submitting"}>
            <legend>Đánh giá câu trả lời</legend>
            <div
              className="feedback-widget__choice interaction-feedbacks"
              role="group"
              aria-label="Đánh giá"
            >
              <button
                className="feedback-widget__choice interaction-feedback"
                type="button"
                aria-label="Thích"
                aria-pressed={value === "LIKE"}
                onClick={() => setValue("LIKE")}
              >
                LIKE
              </button>
              <button
                className="feedback-widget__choice interaction-feedback"
                type="button"
                aria-label="Không thích"
                aria-pressed={value === "DISLIKE"}
                onClick={() => setValue("DISLIKE")}
              >
                DISLIKE
              </button>
            </div>
            <button
              className="feedback-widget__submit interaction-feedback"
              type="submit"
              disabled={!value || state === "submitting"}
              aria-busy={state === "submitting"}
            >
              {state === "submitting" ? "Đang gửi…" : "Gửi đánh giá"}
            </button>
          </fieldset>
          {state === "error" && (
            <p className="feedback-widget__error" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
