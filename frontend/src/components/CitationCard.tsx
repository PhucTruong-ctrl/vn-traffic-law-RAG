"use client";

export type Citation = {
  provision_id: string;
  document_id?: string;
  document_number?: string;
  article?: string;
  parent_context?: string;
  legal_context?: string;
  source_url?: string;
  source_text?: string;
  page_number?: number | string;
  bbox?:
    | number[]
    | { left: number; top: number; right: number; bottom: number };
  document_title?: string;
  clause?: string;
  point?: string;
  version?: string;
  version_date?: string;
  effective_from?: string;
  effective_to?: string | null;
  interval?: { from?: string; to?: string | null };
  snapshot_at?: string;
  snippet?: string;
};

type CitationCardProps = {
  citation: Citation;
  onOpenSource: (citation: Citation) => void;
};

function hasBbox(bbox: Citation["bbox"]): boolean {
  return Array.isArray(bbox) ? bbox.length === 4 : Boolean(bbox);
}

export default function CitationCard({
  citation,
  onOpenSource,
}: CitationCardProps) {
  const sourceText =
    citation.legal_context || citation.source_text || citation.snippet;
  const interval = citation.interval || {
    from: citation.effective_from,
    to: citation.effective_to,
  };
  const sourceUrl = (() => {
    if (!citation.source_url) return undefined;
    try {
      const url = new URL(citation.source_url);
      return url.protocol === "https:" &&
        url.hostname.toLowerCase().endsWith(".chinhphu.vn")
        ? url.toString()
        : undefined;
    } catch {
      return undefined;
    }
  })();
  const unavailable = !citation.document_id;
  const title =
    citation.document_title ||
    citation.document_number ||
    citation.provision_id ||
    "Quy định liên quan";
  const hierarchy = [
    citation.article && `Điều ${citation.article}`,
    citation.clause && `Khoản ${citation.clause}`,
    citation.point && `Điểm ${citation.point}`,
  ].filter(Boolean);

  return (
    <article
      className="citation-card motion-entrance"
      aria-labelledby={`citation-${citation.provision_id}`}
    >
      <header className="citation-card__header">
        <span className="citation-card__eyebrow">CĂN CỨ PHÁP LÝ</span>
        <h3 id={`citation-${citation.provision_id}`}>{title}</h3>
      </header>
      <dl className="citation-card__details">
        <div>
          <dt>Văn bản</dt>
          <dd>
            {citation.document_number
              ? `${title} — ${citation.document_number}`
              : title}
          </dd>
        </div>
        <div>
          <dt>Vị trí quy định</dt>
          <dd>{hierarchy.length ? hierarchy.join(" / ") : "Chưa xác định"}</dd>
        </div>
        {citation.version && (
          <div>
            <dt>Phiên bản</dt>
            <dd>
              {citation.version}
              {citation.version_date ? ` (${citation.version_date})` : ""}
            </dd>
          </div>
        )}
        {(interval.from || interval.to) && (
          <div>
            <dt>Hiệu lực</dt>
            <dd>
              {interval.from || "Không rõ"} đến {interval.to || "nay"}
            </dd>
          </div>
        )}
        {citation.snapshot_at && (
          <div>
            <dt>Ảnh chụp dữ liệu</dt>
            <dd>{citation.snapshot_at}</dd>
          </div>
        )}
      </dl>
      {(citation.page_number != null || citation.bbox != null) && (
        <p className="citation-card__meta">
          {citation.page_number != null && (
            <span>Trang {citation.page_number}</span>
          )}
          {hasBbox(citation.bbox) ? (
            <span>Đã xác định vị trí văn bản</span>
          ) : (
            <span>Chưa có dữ liệu vị trí để tô sáng</span>
          )}
        </p>
      )}
      {citation.legal_context && (
        <section
          className="citation-card__context"
          aria-label="Ngữ cảnh pháp lý nguyên văn"
        >
          <h4>Ngữ cảnh pháp lý (nguyên văn nguồn OCR)</h4>
          <p>{citation.legal_context}</p>
        </section>
      )}
      <div className="citation-card__actions">
        {sourceText && (
          <button
            className="citation-card__source-button interaction-feedback"
            type="button"
            onClick={() =>
              onOpenSource({ ...citation, source_text: sourceText })
            }
          >
            Xem đoạn trích
          </button>
        )}
        {unavailable && sourceText && (
          <span role="note">Không thể mở PDF: chưa có mã tài liệu.</span>
        )}
        {sourceUrl && (
          <a
            className="citation-card__external-link"
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
          >
            Mở nguồn <span aria-hidden="true">↗</span>
          </a>
        )}
      </div>
    </article>
  );
}

