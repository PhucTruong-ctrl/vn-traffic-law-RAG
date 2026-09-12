"use client";

import { ChevronRight } from "lucide-react";
export type Citation = {
  source_id: string;
  document_id: string;
  document_number?: string | null;
  document_title?: string | null;
  document?: string | null;
  provision_id?: string;
  article?: string | null;
  clause?: string | null;
  point?: string | null;
  page?: number | null;
  page_number?: number | string | null;
  source_file?: string | null;
  source_url?: string | null;
  pdf_url?: string | null;
  source_text?: string;
  snippet?: string;
  excerpt: string;
  bbox?: number[] | { left: number; top: number; right: number; bottom: number };
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
          <ChevronRight aria-hidden="true" />
        </span>
      </button>
    </article>
  );
}
