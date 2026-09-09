"use client";

export type Citation = {
  provision_id: string;
  document_number?: string;
  article?: string;
  source_url?: string;
  source_text?: string;
  page_number?: number | string;
  bbox?: number[];
  document_title?: string;
  clause?: string;
  point?: string;
  effective_from?: string;
  effective_to?: string | null;
  interval?: { from?: string; to?: string | null };
  snippet?: string;
};

type CitationCardProps = {
  citation: Citation;
  onOpenSource: (citation: Citation) => void;
};

export default function CitationCard({ citation, onOpenSource }: CitationCardProps) {
  const hasSource = Boolean(citation.source_text || citation.snippet);
  const interval = citation.interval || { from: citation.effective_from, to: citation.effective_to };
  const title = citation.document_title || citation.document_number || citation.provision_id || "Quy định liên quan";
  const provision = [citation.article, citation.clause, citation.point].filter(Boolean).join(" / ");

  return (
    <article className="citation-card motion-entrance" aria-labelledby={`citation-${citation.provision_id}`}>
      <header className="citation-card__header">
        <span className="citation-card__eyebrow">CĂN CỨ PHÁP LÝ</span>
        <h3 id={`citation-${citation.provision_id}`}>{title}</h3>
      </header>
      <dl className="citation-card__details">
        {citation.document_number && (
          <div>
            <dt>Số hiệu</dt>
            <dd>{citation.document_number}</dd>
          </div>
        )}
        <div>
          <dt>Điều / Khoản / Điểm</dt>
          <dd>{provision || "Chưa xác định"}</dd>
        </div>
        {interval.from && (
          <div>
            <dt>Hiệu lực</dt>
            <dd>{interval.from} đến {interval.to || "nay"}</dd>
          </div>
        )}
      </dl>
      {(citation.page_number != null || citation.bbox?.length === 4) && (
        <p className="citation-card__meta">
          {citation.page_number != null && <span>Trang {citation.page_number}</span>}
          {citation.bbox?.length === 4 && <span>Vị trí văn bản</span>}
        </p>
      )}
      <div className="citation-card__actions">
        {hasSource && (
          <button
            className="citation-card__source-button interaction-feedback"
            type="button"
            onClick={() => onOpenSource({ ...citation, source_text: citation.source_text || citation.snippet })}
          >
            Xem đoạn trích
          </button>
        )}
        {citation.source_url && (
          <a className="citation-card__external-link" href={citation.source_url} target="_blank" rel="noreferrer">
            Mở nguồn <span aria-hidden="true">↗</span>
          </a>
        )}
      </div>
    </article>
  );
}
