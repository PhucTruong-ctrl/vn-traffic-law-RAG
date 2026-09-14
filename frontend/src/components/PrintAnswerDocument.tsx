"use client";

import { createPortal } from "react-dom";
import { MarkdownAnswer } from "./ChatThread";
import type { Citation } from "./CitationCard";

type PrintAnswerDocumentProps = {
  answer: string;
  citations: Citation[];
  question: string;
};

export default function PrintAnswerDocument({
  answer,
  citations,
  question,
}: PrintAnswerDocumentProps) {
  if (typeof document === "undefined") return null;

  return createPortal(
    <article className="print-document" aria-hidden="true">
      <header className="print-document__header">
        <div className="print-document__brand">
          <span aria-hidden="true">§</span>
          <strong>VNLAW</strong>
        </div>
        <p>TRỢ LÝ PHÁP LUẬT GIAO THÔNG VIỆT NAM</p>
      </header>

      <section className="print-document__question">
        <p>CÂU HỎI</p>
        <h1>{question}</h1>
      </section>

      <section className="print-document__answer">
        <p className="print-document__label">NỘI DUNG TRẢ LỜI</p>
        <MarkdownAnswer answer={answer} />
      </section>

      {citations.length > 0 && (
        <section className="print-document__citations">
          <h2>Căn cứ pháp lý</h2>
          <ol>
            {citations.map((citation, index) => {
              const title =
                citation.document_title ||
                citation.document ||
                citation.document_number ||
                citation.provision_id ||
                "Văn bản pháp luật";
              const location = [
                citation.article && `Điều ${citation.article}`,
                citation.clause && `Khoản ${citation.clause}`,
                citation.point && `Điểm ${citation.point}`,
                citation.page && `Trang ${citation.page}`,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <li key={`${citation.source_id}-${index}`}>
                  <strong>{title}</strong>
                  {location && <span>{location}</span>}
                  {citation.excerpt && <blockquote>{citation.excerpt}</blockquote>}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <footer className="print-document__footer">
        <span>Được tạo từ VNLAW</span>
        <span>Cần đối chiếu văn bản gốc trước khi áp dụng.</span>
      </footer>
    </article>,
    document.body,
  );
}
