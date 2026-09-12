"use client";

import { useEffect, useRef, useState } from "react";
import type { Citation } from "./CitationCard";
import Modal from "./Modal";
import LegalSourceViewer, { type LegalSourceDocument } from "./LegalSourceViewer";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export default function SourceDrawer({
  citation,
  onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [sourceDocument, setSourceDocument] = useState<LegalSourceDocument | undefined>();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!citation) return;
    const previousFocus =
      globalThis.document.activeElement instanceof HTMLElement
        ? globalThis.document.activeElement
        : null;
    const background = [
      globalThis.document.querySelector<HTMLElement>(".sidebar"),
      globalThis.document.querySelector<HTMLElement>(".main-panel"),
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

  useEffect(() => {
    if (!citation) return;
    const controller = new AbortController();
    void fetch(`${API_BASE}/api/v1/legal-documents/${encodeURIComponent(citation.document_id)}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Không thể tải nội dung nguồn pháp luật.");
        return response.json() as Promise<LegalSourceDocument>;
      })
      .then(setSourceDocument)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setSourceDocument(undefined);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [citation]);

  if (!citation) return null;
  const title =
    citation.document_title ||
    citation.document_number ||
    citation.document_id ||
    "Nguồn pháp luật";

  return (
    <Modal
      open
      onClose={onClose}
      label="Nguồn pháp luật"
      className="source-drawer legal-source-drawer"
    >
      {loading ? (
        <p className="legal-source-viewer__state">Đang tải nội dung nguồn pháp luật…</p>
      ) : (
        <LegalSourceViewer
          citation={citation}
          mode="chat"
          document={
            sourceDocument || {
              document_title: title,
              source_url: citation.source_url,
              pdf_url: citation.pdf_url,
              source_file: citation.source_file,
            }
          }
        />
      )}
    </Modal>
  );
}
