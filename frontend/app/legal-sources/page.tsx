"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Modal from "../../src/components/Modal";
import LegalSourceViewer from "../../src/components/LegalSourceViewer";
import { apiUrl } from "../../src/lib/api";

function responseError(response: Response, fallback: string) {
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
      detail ? `${fallback} (${response.status}): ${detail}` : `${fallback} (${response.status})`,
    );
  });
}

type LegalProvision = {
  id?: string;
  provision_id?: string;
  article?: string;
  clause?: string;
  point?: string;
  title?: string;
  heading?: string;
  text?: string;
  content?: string;
  excerpt?: string;
};

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
  provisions?: LegalProvision[];
  articles?: LegalProvision[];
};

function records(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    const value = payload as Record<string, unknown>;
    for (const key of keys) if (Array.isArray(value[key])) return value[key];
    if (value.data && typeof value.data === "object") return records(value.data, keys);
  }
  return [];
}

function normalize(payload: unknown): LegalDocument[] {
  return records(payload, ["documents", "items", "results", "data"]) as LegalDocument[];
}

function normalizeProvisions(payload: unknown): LegalProvision[] {
  return records(payload, ["provisions", "items", "results", "data"]) as LegalProvision[];
}

function normalizeDocument(payload: unknown): LegalDocument {
  return payload && typeof payload === "object" ? (payload as LegalDocument) : {};
}

function documentId(document: LegalDocument) {
  return document.document_id || document.id || "";
}
function normalizeDocumentNumber(value: unknown) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("vi")
    .replace(/[^a-z0-9]+/gi, "");
}

function documentMatchesNumber(document: LegalDocument, filter: string) {
  const normalizedFilter = normalizeDocumentNumber(filter);
  if (!normalizedFilter) return true;
  return normalizeDocumentNumber(document.document_number).includes(normalizedFilter);
}
function citationSearch(article: string, clause: string, point: string, excerpt: string) {
  return (
    excerpt.trim() ||
    [article && `Điều ${article}`, clause && `khoản ${clause}`, point && `điểm ${point}`]
      .filter(Boolean)
      .join(" ")
  );
}

function provisionText(provision: LegalProvision) {
  return provision.text || provision.content || provision.excerpt || "";
}

function provisionLabel(provision: LegalProvision) {
  return [
    provision.article && `Điều ${provision.article}`,
    provision.clause && `Khoản ${provision.clause}`,
    provision.point && `Điểm ${provision.point}`,
    provision.title || provision.heading,
  ]
    .filter(Boolean)
    .join(" — ");
}

function provisionsMarkdown(provisions: LegalProvision[]) {
  return provisions
    .map((provision) => {
      const label = provisionLabel(provision);
      const text = provisionText(provision);
      return `${label ? `## ${label}\n\n` : ""}${text}`.trim();
    })
    .filter(Boolean)
    .join("\n\n");
}
function LegalSourcesExplorer() {
  const searchParams = useSearchParams();
  const [documents, setDocuments] = useState<LegalDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState(() => searchParams.get("q") || "");
  const [number, setNumber] = useState(() => searchParams.get("document_number") || "");
  const [article, setArticle] = useState(() => searchParams.get("article") || "");
  const [clause, setClause] = useState(() => searchParams.get("clause") || "");
  const [point, setPoint] = useState(() => searchParams.get("point") || "");
  const [selected, setSelected] = useState<LegalDocument | null>(null);
  const [selectedProvisions, setSelectedProvisions] = useState<LegalProvision[]>([]);
  const [selectedLoading, setSelectedLoading] = useState(false);
  const selectedRequest = useRef<{ id: string; controller: AbortController } | null>(null);
  const [selectedError, setSelectedError] = useState("");

  const updateUrl = useCallback((updates: Record<string, string>) => {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(updates)) {
      if (value.trim()) params.set(key, value.trim());
      else params.delete(key);
    }
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, []);

  const selectDocument = useCallback(
    async (
      document: LegalDocument,
      target?: { article?: string; clause?: string; point?: string },
    ) => {
      const id = documentId(document);
      if (!id) return;
      const previousRequest = selectedRequest.current;
      previousRequest?.controller.abort();
      const controller = new AbortController();
      selectedRequest.current = { id, controller };
      const isCurrentRequest = () =>
        selectedRequest.current?.id === id && selectedRequest.current.controller === controller;
      setSelected(document);
      setSelectedProvisions([]);
      setSelectedError("");
      const selectedArticle = target?.article || article;
      const selectedClause = target?.clause || clause;
      const selectedPoint = target?.point || point;
      updateUrl({
        document: id,
        article: selectedArticle,
        clause: selectedClause,
        point: selectedPoint,
      });
      setSelectedLoading(true);
      try {
        const [detailResponse, provisionsResponse] = await Promise.all([
          fetch(apiUrl(`legal-documents/${encodeURIComponent(id)}`), { signal: controller.signal }),
          fetch(
            apiUrl(
              `legal-documents/${encodeURIComponent(id)}/provisions?${new URLSearchParams({
                ...(selectedArticle ? { article: selectedArticle } : {}),
                ...(selectedClause ? { clause: selectedClause } : {}),
                ...(selectedPoint ? { point: selectedPoint } : {}),
              })}`,
            ),
            { signal: controller.signal },
          ),
        ]);
        if (!isCurrentRequest()) return;
        if (!detailResponse.ok)
          await responseError(detailResponse, "Không thể tải nội dung nguồn pháp luật.");
        if (!provisionsResponse.ok)
          await responseError(provisionsResponse, "Không thể tải cấu trúc điều khoản.");
        const [detailPayload, provisionsPayload] = await Promise.all([
          detailResponse.json(),
          provisionsResponse.json(),
        ]);
        if (!isCurrentRequest()) return;
        const detail = normalizeDocument(detailPayload);
        setSelected((current) =>
          documentId(current || {}) === id ? { ...current, ...detail } : current,
        );
        setSelectedProvisions(normalizeProvisions(provisionsPayload));
      } catch (cause) {
        if (!isCurrentRequest() || controller.signal.aborted) return;
        setSelectedError(
          cause instanceof Error ? cause.message : "Không thể tải nội dung nguồn pháp luật.",
        );
      } finally {
        if (isCurrentRequest()) {
          selectedRequest.current = null;
          setSelectedLoading(false);
        }
      }
    },
    [article, clause, point, updateUrl],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      async function load() {
        setLoading(true);
        setError("");
        try {
          const params = new URLSearchParams();
          if (query.trim()) params.set("q", query.trim());
          if (number.trim()) params.set("document_number", number.trim());
          if (article.trim()) params.set("article", article.trim());
          if (clause.trim()) params.set("clause", clause.trim());
          if (point.trim()) params.set("point", point.trim());
          const endpoint =
            query.trim() || article.trim() || clause.trim() || point.trim()
              ? apiUrl(`legal-search?${params.toString()}`)
              : apiUrl("legal-documents");
          const response = await fetch(endpoint, { signal: controller.signal });
          if (!response.ok) await responseError(response, "Không thể tải nguồn pháp luật.");
          setDocuments(
            normalize(await response.json()).filter((document) =>
              documentMatchesNumber(document, number),
            ),
          );
        } catch (cause) {
          if (!controller.signal.aborted)
            setError(cause instanceof Error ? cause.message : "Không thể tải nguồn pháp luật.");
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      }
      void load();
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [article, clause, number, point, query]);

  useEffect(() => {
    const id = searchParams.get("document");
    if (!id || selected || !documents.length) return;
    const match = documents.find((document) => documentId(document) === id);
    if (!match) return;
    const timer = window.setTimeout(() => {
      void selectDocument(match, {
        article: searchParams.get("article") || "",
        clause: searchParams.get("clause") || "",
        point: searchParams.get("point") || "",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [documents, searchParams, selectDocument, selected]);
  const selectedContent = useMemo(() => {
    if (selected?.content || selected?.markdown) return selected;
    if (selectedProvisions.length)
      return { ...selected, markdown: provisionsMarkdown(selectedProvisions) };
    return selected;
  }, [selected, selectedProvisions]);

  const closeSelected = () => {
    selectedRequest.current?.controller.abort();
    selectedRequest.current = null;
    setSelected(null);
    setSelectedProvisions([]);
    setSelectedLoading(false);
    setSelectedError("");
    updateUrl({ document: "", article: "", clause: "", point: "" });
  };
  useEffect(() => {
    return () => {
      selectedRequest.current?.controller.abort();
    };
  }, []);

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
            onChange={(event) => {
              const value = event.target.value;
              setQuery(value);
              updateUrl({ q: value });
            }}
            placeholder="Tên văn bản hoặc nội dung"
          />
        </label>
        <label>
          Số văn bản
          <input
            value={number}
            onChange={(event) => {
              const value = event.target.value;
              setNumber(value);
              updateUrl({ document_number: value });
            }}
            placeholder="Ví dụ: 100/2019/NĐ-CP"
          />
        </label>
        <label>
          Điều
          <input
            value={article}
            onChange={(event) => {
              const value = event.target.value;
              setArticle(value);
              updateUrl({ article: value });
            }}
            placeholder="Ví dụ: 6"
          />
        </label>
        <label>
          Khoản
          <input
            value={clause}
            onChange={(event) => {
              const value = event.target.value;
              setClause(value);
              updateUrl({ clause: value });
            }}
            placeholder="Ví dụ: 2"
          />
        </label>
        <label>
          Điểm
          <input
            value={point}
            onChange={(event) => {
              const value = event.target.value;
              setPoint(value);
              updateUrl({ point: value });
            }}
            placeholder="Ví dụ: a"
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
        {!loading && !error && !documents.length && (
          <p className="legal-sources-page__state">Không tìm thấy văn bản phù hợp.</p>
        )}
        {!loading &&
          !error &&
          documents.map((doc, index) => {
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
                key={`${normalizeDocumentNumber(documentId(doc)) || "document"}-${normalizeDocumentNumber(title)}-${index}`}
                onClick={() => void selectDocument(doc)}
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
        onClose={closeSelected}
        label="Chi tiết nguồn pháp luật"
        className="legal-source-modal"
      >
        {selected &&
          (selectedLoading ? (
            <p className="legal-source-viewer__state">Đang tải nội dung nguồn pháp luật…</p>
          ) : selectedError ? (
            <p className="legal-source-viewer__state" role="alert">
              {selectedError}
            </p>
          ) : (
            <LegalSourceViewer
              mode="explorer"
              searchQuery={citationSearch(
                article,
                clause,
                point,
                selectedContent?.content || selectedContent?.markdown || "",
              )}
              citation={{
                source_id: `${documentId(selected)}:explorer`,
                document_id: documentId(selected) || "selected-document",
                document_title: selected.document_name || selected.title || selected.document_title,
                document_number: selected.document_number,
                article,
                clause,
                point,
                source_url: selected.source?.source_url ?? selected.source_url,
                pdf_url: selected.source?.pdf_url ?? selected.pdf_url,
                source_file: selected.source?.source_file ?? selected.source_file,
                excerpt: selectedContent?.content || selectedContent?.markdown || "",
              }}
              document={selectedContent || undefined}
            />
          ))}
      </Modal>
    </main>
  );
}

export default function LegalSourcesPage() {
  return (
    <Suspense fallback={<main className="legal-sources-page" aria-busy="true" />}>
      <LegalSourcesExplorer />
    </Suspense>
  );
}
