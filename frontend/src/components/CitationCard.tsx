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

export default function CitationCard({ citation, onOpenSource }: { citation: Citation; onOpenSource: (citation: Citation) => void }) {
  const hasSource = Boolean(citation.source_text || citation.snippet);
  const interval = citation.interval || { from: citation.effective_from, to: citation.effective_to };
  return (
    <article className="citation-card">
      <strong>{citation.document_title || citation.document_number || citation.provision_id || "Quy định liên quan"}</strong>
      <div>{citation.document_number && <span>Số hiệu: {citation.document_number}</span>}</div>
      <div>Điều/Khoản/Điểm: {[citation.article, citation.clause, citation.point].filter(Boolean).join(" / ") || "—"}</div>
      {interval.from && <div>Hiệu lực: {interval.from} → {interval.to || "nay"}</div>}
      <div className="citation-meta">
        {citation.page_number != null && <span>Trang {citation.page_number}</span>}
        {citation.bbox?.length === 4 && <span> · Vị trí văn bản</span>}
      </div>
      {hasSource && <button type="button" onClick={() => onOpenSource({...citation, source_text: citation.source_text || citation.snippet})}>Xem đoạn trích</button>}
      {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Mở nguồn</a>}
    </article>
  );
}
