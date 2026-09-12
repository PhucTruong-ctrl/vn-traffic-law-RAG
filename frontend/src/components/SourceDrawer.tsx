"use client";

import { useEffect, useRef, useState } from "react";
import type { Citation } from "./CitationCard";
import Modal from "./Modal";
import LegalSourceViewer, { type LegalSourceDocument } from "./LegalSourceViewer";
import { apiUrl } from "../lib/api";

function responseError(response: Response) {
  return response.text().then((body) => {
    let detail = "";
    try {
      const payload = JSON.parse(body) as { detail?: unknown; message?: unknown };
      detail =
        typeof payload.detail === "string"
          ? payload.detail
          : typeof payload.message === "string"
            ? payload.message
            : "";
    } catch {
      detail = body.trim();
    }
    throw new Error(
      detail
        ? `Không thể tải nội dung nguồn pháp luật (${response.status}): ${detail}`
        : `Không thể tải nội dung nguồn pháp luật (${response.status})`,
    );
  });
}
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
  const [error, setError] = useState("");
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
    const timer = window.setTimeout(() => {
      setLoading(true);
      setSourceDocument(undefined);
      fetch(apiUrl(`legal-documents/${encodeURIComponent(citation.document_id)}`), {
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) return responseError(response);
          return response.json() as Promise<LegalSourceDocument | { data?: LegalSourceDocument }>;
        })
        .then((payload) => {
          if (!controller.signal.aborted) {
            const document =
              payload && typeof payload === "object" && "data" in payload
                ? payload.data
                : (payload as LegalSourceDocument);
            setSourceDocument(document || undefined);
          }
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          if (!controller.signal.aborted)
            setError(
              reason instanceof Error ? reason.message : "Không thể tải nội dung nguồn pháp luật.",
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
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
      ) : error ? (
        <p className="legal-source-viewer__state" role="alert">
          {error}
        </p>
      ) : (
        <LegalSourceViewer
          citation={citation}
          mode="chat"
          document={
            sourceDocument || {
              document_title: title,
              document_id: citation.document_id || citation.document || undefined,
              article: citation.article,
              clause: citation.clause,
              point: citation.point,
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
