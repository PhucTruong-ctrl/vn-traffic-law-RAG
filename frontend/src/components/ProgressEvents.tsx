import React from "react";

export type ProgressEvent = { event?: string; type?: string; message?: string; detail?: string; status?: string };
export type ProgressEventsProps = { events?: ProgressEvent[] | null };

const DEFAULT_STEPS = [
  { label: "Tìm văn bản liên quan", state: "complete", icon: "✓" },
  { label: "Đối chiếu điều luật", state: "active", icon: "" },
  { label: "Tổng hợp câu trả lời", state: "pending", icon: "✦" },
] as const;

export default function ProgressEvents({ events }: ProgressEventsProps) {
  const steps = events?.length
    ? events.map((item, index) => ({ label: item.message || item.detail || item.event || item.type || "Đang xử lý", state: index === events.length - 1 ? "active" : "complete", icon: index === events.length - 1 ? "" : "✓" }))
    : DEFAULT_STEPS;
  return (
    <section className="progress-events-panel" aria-label="Tiến trình xử lý" aria-live="polite">
      <div className="progress-events__skeleton" aria-hidden="true"><span /><span /><span /></div>
      <ol className="progress-events">
        {steps.map((step, index) => (
          <li className={`progress-events__item progress-events__item--${step.state}`} key={`${step.label}-${index}`}>
            <span className="progress-events__marker" aria-hidden="true">{step.icon || <span className="progress-events__spinner" />}</span>
            <span className="progress-events__label">{step.label}</span>
            {step.state === "active" && <span className="progress-events__shimmer" aria-hidden="true" />}
          </li>
        ))}
      </ol>
    </section>
  );
}
