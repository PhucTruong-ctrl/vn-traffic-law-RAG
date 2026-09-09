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
    <section className="progress-events-panel motion-entrance" aria-labelledby="progress-events-title" aria-live="polite">
      <div className="progress-events-panel motion-entrance__header">
        <span className="progress-events-panel motion-entrance__eyebrow">NHẬT KÝ XỬ LÝ</span>
        <h2 id="progress-events-title">Tiến trình xử lý</h2>
      </div>
      <ol className="progress-events">
        {events.map((item, index) => {
          const label = item.message || item.detail || item.event || item.type || "Đang xử lý";
          return (
            <li className="progress-events__item motion-entrance-item" key={`${item.event || item.type || "event"}-${index}`}>
              <span className="progress-events__marker" aria-hidden="true" />
              <span className="progress-events__content">
                <span className="progress-events__label">{label}</span>
                {item.status && <span className="progress-events__status">{item.status}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
