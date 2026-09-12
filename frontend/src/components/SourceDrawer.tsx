"use client";

import { useEffect, useRef } from "react";
import type { Citation } from "./CitationCard";
import Modal from "./Modal";
import LegalSourceViewer from "./LegalSourceViewer";

export default function SourceDrawer({
  citation,
  onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!citation) return;
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const background = [
      document.querySelector<HTMLElement>(".sidebar"),
      document.querySelector<HTMLElement>(".main-panel"),
    ].filter((element): element is HTMLElement => element !== null);
    const previousInert = background.map((element) => element.hasAttribute("inert"));
    background.forEach((element) => element.setAttribute("inert", ""));
    closeButtonRef.current?.focus();
    return () => {
      background.forEach((element, index) => {
        if (!previousInert[index]) element.removeAttribute("inert");
      });
      previousFocus?.focus();
    };
  }, [citation]);

  if (!citation) return null;
  const title =
    citation.document_title ||
    citation.document_number ||
    citation.document_id ||
    "Nguồn pháp luật";
  const excerpt = citation.excerpt.replace(/\r?\n/g, "\n");
  const parentContext = "";

  return (
    <Modal
      open={Boolean(citation)}
      onClose={onClose}
      label="Nguồn pháp luật"
      className="source-drawer pdf-source-drawer"
    >
      <header className="source-drawer__header">
        <div>
          <span className="source-drawer__eyebrow">NGUỒN TRÍCH DẪN</span>
          <h2>{title}</h2>
          {citation.page !== null && citation.page !== undefined && (
            <p className="source-drawer__document">Trang {citation.page}</p>
          )}
        </div>
      </header>
      <div className="source-drawer__body">
        <LegalSourceViewer citation={citation} mode="chat" />
        <details className="source-excerpt">
          <summary>Đọc đoạn trích nguyên văn</summary>
          <blockquote>{excerpt || "Nguồn không cung cấp nội dung đoạn trích."}</blockquote>
        </details>
        {parentContext && (
          <details className="source-excerpt">
            <summary>Ngữ cảnh điều khoản cha</summary>
            <blockquote>{parentContext}</blockquote>
          </details>
        )}
      </div>
      <footer className="source-drawer__footer">
        <button
          ref={closeButtonRef}
          className="source-drawer__done"
          type="button"
          onClick={onClose}
        >
          Đóng
        </button>
        {citation.source_url && (
          <a href={citation.source_url} target="_blank" rel="noreferrer">
            Mở bản gốc ↗
          </a>
        )}
      </footer>
    </Modal>
  );
}
