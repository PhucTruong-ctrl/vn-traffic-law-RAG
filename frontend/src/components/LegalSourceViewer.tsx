"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Clipboard } from "lucide-react";
import type { Citation } from "./CitationCard";
import PdfCitationViewer from "./PdfCitationViewer";

type SourceKind = "markdown" | "pdf";
export type LegalSourceDocument = {
  title?: string | null;
  document_name?: string | null;
  document_title?: string | null;
  source?: {
    source_file?: string | null;
    source_url?: string | null;
    pdf_url?: string | null;
    source_kind?: SourceKind;
    document_id?: string | null;
  };
  document_id?: string | null;
  provision_id?: string | null;
  article?: string | number | null;
  clause?: string | number | null;
  point?: string | null;
  chunk_id?: string | null;
  chunk_index?: number | null;
  article_number?: string | number | null;
  clause_number?: string | number | null;
  point_number?: string | null;
  source_kind?: SourceKind;
  content?: string | null;
  markdown?: string | null;
  pdf_url?: string | null;
  source_url?: string | null;
  source_file?: string | null;
};

type Props = {
  citation: Citation;
  document?: LegalSourceDocument;
  mode?: "chat" | "explorer";
  searchQuery?: string;
};

type MarkdownBlock = { id: string; level: number; title?: string; text: string };
export default function LegalSourceViewer({
  citation,
  document,
  mode = "chat",
  searchQuery,
}: Props) {
  const source = document?.source;
  const merged = {
    ...citation,
    ...document,
    document_id: document?.document_id || citation.document_id,
    provision_id: document?.provision_id ?? citation.provision_id,
    source_kind: source?.source_kind ?? document?.source_kind,
    pdf_url: source?.pdf_url ?? document?.pdf_url ?? citation.pdf_url,
    source_url: source?.source_url ?? document?.source_url ?? citation.source_url,
    source_file: source?.source_file ?? document?.source_file ?? citation.source_file,
  };
  const kind: SourceKind =
    merged.source_kind ??
    (merged.pdf_url || /\.pdf(?:$|[?#])/i.test(merged.source_url || merged.source_file || "")
      ? "pdf"
      : "markdown");
  if (kind === "pdf") {
    return (
      <PdfCitationViewer
        citation={{ ...merged, provision_id: merged.provision_id ?? undefined } as Citation}
      />
    );
  }
  return (
    <MarkdownSourceViewer
      citation={citation}
      document={
        { ...merged, provision_id: merged.provision_id ?? undefined } as LegalSourceDocument &
          Citation
      }
      mode={mode}
      searchQuery={searchQuery}
    />
  );
}

function MarkdownSourceViewer({
  citation,
  document,
  mode,
  searchQuery,
}: {
  citation: Citation;
  document: LegalSourceDocument & Citation;
  mode: "chat" | "explorer";
  searchQuery?: string;
}) {
  const raw =
    document.markdown ??
    document.content ??
    citation.source_text ??
    citation.excerpt ??
    citation.snippet ??
    "";
  const visibleRaw = raw.replace(/\r\n?/g, "\n").replace(/\A---\s*\n[\s\S]*?(?:\n---\s*\n|\Z)/, "");
  const blocks = useMemo(() => parseMarkdown(visibleRaw), [visibleRaw]);

  const [query, setQuery] = useState(searchQuery ?? "");
  const querySource = useRef(searchQuery);
  useEffect(() => {
    if (querySource.current === searchQuery) return;
    querySource.current = searchQuery;
    setQuery(searchQuery ?? "");
  }, [searchQuery]);
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const target = useMemo(() => {
    if (mode === "chat") {
      return (
        citation.source_text ?? citation.excerpt ?? citation.snippet ?? citation.provision_id ?? ""
      );
    }
    return searchQuery?.trim() || "";
  }, [citation, mode, searchQuery]);
  const findTarget = useCallback((container: HTMLElement, term: string): HTMLElement | null => {
    const needle = term.trim().toLocaleLowerCase();
    if (!needle) return null;
    return (
      Array.from(container.querySelectorAll<HTMLElement>("[data-source-text]")).find((node) =>
        (node.dataset.sourceText || "").toLocaleLowerCase().includes(needle),
      ) ??
      Array.from(container.querySelectorAll<HTMLElement>("[data-article]")).find((node) => {
        const reference = [
          node.dataset.article && `điều ${node.dataset.article}`,
          node.dataset.clause && `khoản ${node.dataset.clause}`,
          node.dataset.point && `điểm ${node.dataset.point}`,
        ]
          .filter(Boolean)
          .join(" ");
        return reference.toLocaleLowerCase().includes(needle);
      }) ??
      null
    );
  }, []);
  useEffect(() => {
    const container = contentRef.current;
    if (!container) return;
    const match = findTarget(container, mode === "chat" ? target : query);
    match?.scrollIntoView({ block: "center" });
  }, [mode, query, target, blocks, findTarget]);
  const matches = (mode === "chat" ? target : query).trim().toLowerCase();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="legal-source-viewer markdown-viewer" aria-label="Văn bản pháp luật">
      <header className="markdown-viewer__header">
        <div>
          <p className="markdown-viewer__eyebrow">Văn bản pháp luật</p>
          <h2>{document.document_title || document.title || "Nguồn pháp luật"}</h2>
        </div>
        <div className="markdown-viewer__actions">
          {(document.source_url || document.pdf_url) && (
            <a
              className="markdown-viewer__original"
              href={document.source_url || document.pdf_url || undefined}
              target="_blank"
              rel="noreferrer"
            >
              Mở bản gốc
            </a>
          )}
          <button
            type="button"
            onClick={() => void copy()}
            className="markdown-viewer__copy"
            aria-label={copied ? "Đã sao chép văn bản" : "Sao chép văn bản"}
          >
            {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
            {copied ? "Đã sao chép" : "Sao chép"}
          </button>
        </div>
      </header>
      <div className="markdown-viewer__toolbar">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Tìm trong văn bản"
          aria-label="Tìm trong văn bản"
        />
      </div>
      {blocks.some((block) => block.level > 0) && (
        <nav className="markdown-viewer__outline" aria-label="Mục lục văn bản">
          {blocks
            .filter((block) => block.level > 0)
            .map((block) => (
              <a key={block.id} href={`#${block.id}`}>
                {block.title}
              </a>
            ))}
        </nav>
      )}
      <div ref={contentRef} className="markdown-viewer__content">
        {blocks.map((block) => {
          const highlighted = matches && block.text.toLowerCase().includes(matches);
          const cited = Boolean(
            target && block.text.toLowerCase().includes(target.trim().toLowerCase()),
          );
          return (
            <div
              key={block.id}
              id={block.id}
              data-source-text={block.text}
              data-provision-id={document.provision_id ?? citation.provision_id}
              data-chunk-id={document.chunk_id}
              data-chunk-index={document.chunk_index}
              data-article={document.article ?? document.article_number ?? citation.article}
              data-clause={document.clause ?? document.clause_number ?? citation.clause}
              data-point={document.point ?? document.point_number ?? citation.point}
              className={`${highlighted ? "markdown-viewer__match" : ""} ${cited ? "markdown-viewer__citation" : ""}`}
            >
              {block.level > 0 ? (
                <Heading level={block.level} title={block.title ?? block.text} />
              ) : (
                <p>{block.text}</p>
              )}
            </div>
          );
        })}
        {!blocks.length && (
          <p className="markdown-viewer__empty">Nguồn chưa cung cấp nội dung Markdown.</p>
        )}
      </div>
    </section>
  );
}

function Heading({ level, title }: { level: number; title: string }) {
  const heading = Math.min(6, Math.max(1, level));
  return (
    <Fragment>
      {heading === 1 && <h1>{title}</h1>}
      {heading === 2 && <h2>{title}</h2>}
      {heading === 3 && <h3>{title}</h3>}
      {heading === 4 && <h4>{title}</h4>}
      {heading === 5 && <h5>{title}</h5>}
      {heading === 6 && <h6>{title}</h6>}
    </Fragment>
  );
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const body = markdown.replace(/\r\n?/g, "\n").replace(/^---\s*\n[\s\S]*?(?:\n---\s*\n|$)/, "");
  return body
    .split(/\n{2,}/)
    .map((part, index) => {
      const text = part.trim();
      const heading = text.match(/^(#{1,6})\s+([\s\S]+)$/);
      const title = heading?.[2]?.trim();
      return {
        id: `source-section-${index + 1}`,
        level: heading?.[1].length ?? 0,
        title,
        text: title ?? text,
      };
    })
    .filter((block) => block.text);
}
