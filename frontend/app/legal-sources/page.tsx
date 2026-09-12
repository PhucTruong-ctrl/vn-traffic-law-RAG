"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Modal from "../../src/components/Modal";
import LegalSourceViewer from "../../src/components/LegalSourceViewer";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

type LegalDocument = {
  id?: string;
  document_id?: string;
  document_name?: string;
  title?: string;
  document_title?: string;
  document_number?: string;
  provision_count?: number;
  source?: {
    source_kind?: "markdown" | "pdf";
    pdf_url?: string;
    source_url?: string;
    source_file?: string;
  };
  source_kind?: "markdown" | "pdf";
  content?: string;
  markdown?: string;
  source_url?: string;
  pdf_url?: string;
  source_file?: string;
  articles?: Array<{
    id?: string;
    article?: string;
    title?: string;
    text?: string;
    content?: string;
  }>;
};

function normalize(payload: unknown): LegalDocument[] {
  if (Array.isArray(payload)) return payload as LegalDocument[];
  if (payload && typeof payload === "object") {
    const value = payload as Record<string, unknown>;
    for (const key of ["documents", "items", "results", "data"]) {
      if (Array.isArray(value[key])) return value[key] as LegalDocument[];
    }
  }
  return [];
}

export default function LegalSourcesPage() {
  const [documents, setDocuments] = useState<LegalDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [number, setNumber] = useState("");
  const [article, setArticle] = useState("");
  const [selected, setSelected] = useState<LegalDocument | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE}/api/v1/legal-documents`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Không thể tải danh sách nguồn pháp luật.");
        setDocuments(normalize(await response.json()));
      } catch (cause) {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : "Không thể tải nguồn pháp luật.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  const filtered = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase();
    const docNumber = number.trim().toLocaleLowerCase();
    const articleTerm = article.trim().toLocaleLowerCase();
    return documents.filter((doc) => {
      const haystack = [
        doc.document_name,
        doc.title,
        doc.document_title,
        doc.document_number,
        doc.markdown,
        doc.content,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return (
        (!terms || haystack.includes(terms)) &&
        (!docNumber || (doc.document_number || "").toLocaleLowerCase().includes(docNumber)) &&
        (!articleTerm ||
          haystack.includes(articleTerm) ||
          (doc.articles || []).some((item) =>
            [item.article, item.title, item.text, item.content]
              .filter(Boolean)
              .join(" ")
              .toLocaleLowerCase()
              .includes(articleTerm),
          ))
      );
    });
  }, [documents, query, number, article]);

  return (
    <main className="legal-sources-page">
      <header className="legal-sources-page__header">
        <div>
          <Link href="/chat" className="legal-sources-page__back">
            ← Trợ lý
          </Link>
          <p className="eyebrow">THƯ VIỆN PHÁP LUẬT</p>
          <h1>Nguồn pháp luật</h1>
          <p>Tra cứu văn bản và điều khoản được sử dụng trong hệ thống.</p>
        </div>
      </header>
      <section className="legal-sources-page__filters" aria-label="Bộ lọc nguồn pháp luật">
        <label>
          Từ khóa
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tên văn bản hoặc nội dung"
          />
        </label>
        <label>
          Số văn bản
          <input
            value={number}
            onChange={(event) => setNumber(event.target.value)}
            placeholder="Ví dụ: 100/2019/NĐ-CP"
          />
        </label>
        <label>
          Điều, khoản, điểm
          <input
            value={article}
            onChange={(event) => setArticle(event.target.value)}
            placeholder="Ví dụ: Điều 6"
          />
        </label>
      </section>
      <section className="legal-sources-page__results" aria-live="polite">
        {loading && <p className="legal-sources-page__state">Đang tải nguồn pháp luật…</p>}
        {!loading && error && (
          <div className="legal-sources-page__state" role="alert">
            <p>{error}</p>
            <button type="button" onClick={() => window.location.reload()}>
              Thử lại
            </button>
          </div>
        )}
        {!loading && !error && !filtered.length && (
          <p className="legal-sources-page__state">Không tìm thấy văn bản phù hợp.</p>
        )}
        {!loading &&
          !error &&
          filtered.map((doc, index) => {
            const title =
              doc.document_name ||
              doc.title ||
              doc.document_title ||
              doc.document_number ||
              "Văn bản pháp luật";
            const sourceKind = doc.source?.source_kind ?? doc.source_kind;
            return (
              <button
                type="button"
                className="legal-source-card"
                key={doc.id || doc.document_id || `${title}-${index}`}
                onClick={() => setSelected(doc)}
              >
                <span className="legal-source-card__kind">
                  {sourceKind === "markdown" ? "MARKDOWN" : "PDF"}
                </span>
                <strong>{title}</strong>
                {doc.document_number && <span>{doc.document_number}</span>}
                {typeof doc.provision_count === "number" && (
                  <span>{doc.provision_count} điều khoản</span>
                )}
                <span className="legal-source-card__open">Mở văn bản →</span>
              </button>
            );
          })}
      </section>
      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        label="Chi tiết nguồn pháp luật"
        className="legal-source-modal"
      >
        {selected && (
          <LegalSourceViewer
            mode="explorer"
            citation={{
              source_id: `${selected.document_id}:explorer`,
              document_id: selected.document_id || selected.id || "selected-document",
              document_title: selected.document_name || selected.title || selected.document_title,
              document_number: selected.document_number,
              source_url: selected.source?.source_url ?? selected.source_url,
              pdf_url: selected.source?.pdf_url ?? selected.pdf_url,
              source_file: selected.source?.source_file ?? selected.source_file,
              excerpt: selected.content || selected.markdown || "",
            }}
            document={selected}
          />
        )}
      </Modal>
    </main>
  );
}
