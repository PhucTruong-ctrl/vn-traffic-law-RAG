
export type ProgressEvent = {
  event?: string;
  type?: string;
  message?: string;
  detail?: string;
  status?: string;
};

const NEUTRAL_STATUS = "Đang xử lý yêu cầu…";
export type ProgressEventsProps = {
  events?: ProgressEvent[] | null;
  loading: boolean;
};

export default function ProgressEvents({ events, loading }: ProgressEventsProps) {
  if (!loading) return null;
  const latestEventMessage = (events ?? [])
    .map((event) => event.message || event.detail)
    .filter((message): message is string => Boolean(message))
    .at(-1);
  return (
    <section className="progress-events-panel" aria-label="Tiến trình xử lý" aria-live="polite">
      <div className="progress-events__skeleton" aria-hidden="true"><span /><span /><span /></div>
      <p className="progress-events__event" role="status">
        {latestEventMessage || NEUTRAL_STATUS}
      </p>
    </section>
  );
}
