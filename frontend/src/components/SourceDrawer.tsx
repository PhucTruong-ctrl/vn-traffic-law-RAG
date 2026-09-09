"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import type { Citation } from "./CitationCard";
import PdfCitationViewer from "./PdfCitationViewer";
import { motionTransition } from "./motion";

export default function SourceDrawer({
  citation,
  onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  const shouldReduceMotion = useReducedMotion();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
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
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const controls = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button, a[href], input, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((item) => !item.hasAttribute("disabled"));
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      background.forEach((element, index) => {
        if (!previousInert[index]) element.removeAttribute("inert");
      });
      previousFocus?.focus();
    };
  }, [citation, onClose]);
  const title =
    citation?.document_title ||
    citation?.document_number ||
    citation?.provision_id ||
    "Nguồn pháp luật";
  const excerpt = (
    citation?.legal_context ||
    citation?.source_text ||
    citation?.snippet ||
    ""
  ).replace(/\r?\n/g, "\n");
  return (
    <AnimatePresence>
      {citation && (
        <motion.div
          key="source-drawer-backdrop"
          className="drawer-backdrop"
          role="presentation"
          initial={shouldReduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={shouldReduceMotion ? undefined : { opacity: 0 }}
          transition={motionTransition}
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <motion.aside
            ref={dialogRef}
            className="source-drawer pdf-source-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-title"
            initial={shouldReduceMotion ? false : { opacity: 0, x: "100%" }}
            animate={{ opacity: 1, x: 0 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, x: "100%" }}
            transition={motionTransition}
          >
            <header className="source-drawer__header">
              <div>
                <span className="source-drawer__eyebrow">NGUỒN TRÍCH DẪN</span>
                <h2 id="source-title">{title}</h2>
                <p className="source-drawer__document">Trang {citation.page_number || 1}</p>
              </div>
              <button
                ref={closeButtonRef}
                className="source-drawer__close"
                type="button"
                onClick={onClose}
                aria-label="Đóng trình xem PDF"
              >
                <span aria-hidden="true">×</span>
              </button>
            </header>
            <div className="source-drawer__body">
              <PdfCitationViewer citation={citation} />
              <details className="source-excerpt">
                <summary>Đọc đoạn trích dạng văn bản</summary>
                <blockquote>{excerpt || "Nguồn không cung cấp nội dung đoạn trích."}</blockquote>
              </details>
            </div>
            <footer className="source-drawer__footer">
              <button className="source-drawer__done" type="button" onClick={onClose}>
                Đóng
              </button>
              {citation.source_url && (
                <a href={citation.source_url} target="_blank" rel="noreferrer">
                  Mở bản gốc ↗
                </a>
              )}
            </footer>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
