"use client";

import { Citation } from "./CitationCard";

export default function SourceDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  if (!citation) return null;
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} aria-label="Đóng">×</button>
        <h2 id="source-title">Đoạn trích nguồn</h2>
        <p>{citation.source_text || "Không có nội dung đoạn trích."}</p>
        {citation.page_number != null && <p><strong>Trang:</strong> {citation.page_number}</p>}
        {citation.bbox?.length === 4 && <p><strong>Bounding box:</strong> {citation.bbox.join(", ")}</p>}
      </aside>
    </div>
  );
}
