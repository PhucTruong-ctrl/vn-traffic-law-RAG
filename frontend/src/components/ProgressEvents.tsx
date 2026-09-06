import React from "react";

export type ProgressEvent = {
  event?: string;
  type?: string;
  message?: string;
  detail?: string;
  status?: string;
};

export type ProgressEventsProps = {
  events?: ProgressEvent[] | null;
};

export default function ProgressEvents({ events }: ProgressEventsProps) {
  if (!events?.length) return null;

  return (
    <section aria-labelledby="progress-events-title" aria-live="polite">
      <h2 id="progress-events-title">Tiến trình xử lý</h2>
      <ol className="progress-events">
        {events.map((item, index) => {
          const label = item.message || item.detail || item.event || item.type || "Đang xử lý";
          const state = item.status ? ` (${item.status})` : "";
          return <li key={`${item.event || item.type || "event"}-${index}`}>{label}{state}</li>;
        })}
      </ol>
    </section>
  );
}
