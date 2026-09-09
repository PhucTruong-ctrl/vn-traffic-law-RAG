"use client";

import { useEffect, useRef } from "react";
import { Citation } from "./CitationCard";

export default function SourceDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!citation) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [citation, onClose]);

  if (!citation) return null;
  const title = citation.document_title || citation.document_number || citation.provision_id || "Đoạn trích nguồn";

  return (
    <div className="drawer-backdrop motion-entrance" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-title" aria-describedby="source-excerpt">
        <header className="source-drawer__header">
          <div>
            <span className="source-drawer__eyebrow">NGUỒN TRÍCH DẪN</span>
            <h2 id="source-title">Đoạn trích nguồn</h2>
            <p className="source-drawer__document">{title}</p>
          </div>
          <button ref={closeButtonRef} className="source-drawer__close interaction-feedback" type="button" onClick={onClose} aria-label="Đóng đoạn trích nguồn">
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="source-drawer__body">
          <blockquote id="source-excerpt">{citation.source_text || "Không có nội dung đoạn trích."}</blockquote>
          {(citation.page_number != null || citation.bbox?.length === 4) && (
            <dl className="source-drawer__metadata">
              {citation.page_number != null && <div><dt>Trang</dt><dd>{citation.page_number}</dd></div>}
              {citation.bbox?.length === 4 && <div><dt>Vị trí văn bản</dt><dd>{citation.bbox.join(", ")}</dd></div>}
            </dl>
          )}
        </div>
        <footer className="source-drawer__footer">
          <button className="source-drawer__done interaction-feedback" type="button" onClick={onClose}>Đóng</button>
          {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Mở văn bản gốc <span aria-hidden="true">↗</span></a>}
        </footer>
      </aside>
    </div>
  );
}
