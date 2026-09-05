"use client";

import { FormEvent, useState } from "react";

type FeedbackValue = "useful" | "not_useful";
type SubmissionState = "idle" | "submitting" | "success" | "error";

export type FeedbackWidgetProps = {
  traceId: string;
  endpoint?: string;
};

const MAX_COMMENT_LENGTH = 2_000;

export default function FeedbackWidget({
  traceId,
  endpoint = "/api/v1/feedback",
}: FeedbackWidgetProps) {
  const [value, setValue] = useState<FeedbackValue | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<SubmissionState>("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!value || !traceId || state === "submitting") return;

    setState("submitting");
    setError(null);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Trace-ID": traceId,
        },
        body: JSON.stringify({
          trace_id: traceId,
          useful: value === "useful",
          comment: comment.trim() || null,
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        throw new Error(payload?.error?.message || "Không thể gửi phản hồi.");
      }

      setState("success");
    } catch (submissionError) {
      setState("error");
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Không thể gửi phản hồi.",
      );
    }
  }

  return (
    <section aria-labelledby="feedback-heading">
      <h2 id="feedback-heading">Phản hồi câu trả lời</h2>
      {state === "success" ? (
        <p role="status">Cảm ơn bạn đã gửi phản hồi.</p>
      ) : (
        <form onSubmit={submit}>
          <fieldset disabled={state === "submitting"}>
            <legend>Câu trả lời này có hữu ích không?</legend>
            <div>
              <button
                type="button"
                aria-pressed={value === "useful"}
                onClick={() => setValue("useful")}
              >
                Hữu ích
              </button>{" "}
              <button
                type="button"
                aria-pressed={value === "not_useful"}
                onClick={() => setValue("not_useful")}
              >
                Chưa hữu ích
              </button>
            </div>
            <label htmlFor="feedback-comment">Bình luận (không bắt buộc)</label>
            <textarea
              id="feedback-comment"
              name="comment"
              value={comment}
              maxLength={MAX_COMMENT_LENGTH}
              onChange={(event) => setComment(event.target.value)}
              rows={4}
            />
            <button type="submit" disabled={!value || state === "submitting"}>
              {state === "submitting" ? "Đang gửi…" : "Gửi phản hồi"}
            </button>
          </fieldset>
          {state === "error" && (
            <p role="alert">{error}</p>
          )}
        </form>
      )}
    </section>
  );
}
