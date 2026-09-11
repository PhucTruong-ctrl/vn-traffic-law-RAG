"use client";

export type Citation = {
  provision_id?: string;
  document_id?: string;
  document_number?: string;
  document?: string;
  article?: string;
  parent_context?: string;
  legal_context?: string;
  source_url?: string;
  source_text?: string;
  excerpt?: string;
  page_number?: number | string;
  page?: number | string;
  source_file?: string;
  pdf_url?: string;
  bbox?: number[] | { left: number; top: number; right: number; bottom: number };
  document_title?: string;
  clause?: string;
  point?: string;
  version?: string;
  provision_version?: number;
  version_date?: string;
  effective_from?: string;
  effective_to?: string | null;
  interval?: { from?: string; to?: string | null };
  snapshot_at?: string;
  content_hash?: string;
  snippet?: string;
};

type CitationCardProps = {
  citation: Citation;
  onOpenSource: (citation: Citation) => void;
};

export default function CitationCard({ citation, onOpenSource }: CitationCardProps) {
  const title =
    citation.document_title ||
    citation.document ||
    citation.document_number ||
    citation.provision_id ||
    "Quy định liên quan";
  const hierarchy = [
    citation.article && `Điều ${citation.article}`,
    citation.clause && `Khoản ${citation.clause}`,
    citation.point && `Điểm ${citation.point}`,
  ].filter(Boolean);
  const sourceType =
    citation.pdf_url || citation.source_url ? "PDF / nguồn trực tuyến" : "Nguồn dữ liệu";

  return (
    <article className="citation-card citation-card--compact">
      <button
        className="citation-card__button"
        type="button"
        onClick={() => onOpenSource(citation)}
        aria-label={`Mở chi tiết nguồn: ${title}`}
      >
        <span className="citation-card__index" aria-hidden="true">
          {citation.provision_id ? "§" : "•"}
        </span>
        <span className="citation-card__summary">
          <strong>{title}</strong>
          <span>{hierarchy.length ? hierarchy.join(" / ") : "Chưa xác định vị trí"}</span>
          <small>{sourceType}</small>
        </span>
        <span className="citation-card__chevron" aria-hidden="true">
          ›
        </span>
      </button>
    </article>
  );
}
