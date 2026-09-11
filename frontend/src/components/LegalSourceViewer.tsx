"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { Citation } from "./CitationCard";
import PdfCitationViewer from "./PdfCitationViewer";

type SourceKind = "markdown" | "pdf";
export type LegalSourceDocument = {
  title?: string;
  source?: {
    source_kind?: SourceKind;
    pdf_url?: string;
    source_url?: string;
    source_file?: string;
  };
  source_kind?: SourceKind;
  content?: string;
  markdown?: string;
  pdf_url?: string;
  source_url?: string;
  source_file?: string;
};

type Props = {
  citation: Citation;
  document?: LegalSourceDocument;
  mode?: "chat" | "explorer";
};

type MarkdownBlock = { id: string; level: number; title?: string; text: string };

export default function LegalSourceViewer({ citation, document, mode = "chat" }: Props) {
  const source = document?.source;
  const merged = {
    ...citation,
    ...document,
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
    return <PdfCitationViewer citation={merged} />;
  }
  return <MarkdownSourceViewer citation={citation} document={merged} mode={mode} />;
}

function MarkdownSourceViewer({
  citation,
  document,
  mode,
}: {
  citation: Citation;
  document: LegalSourceDocument & Citation;
  mode: "chat" | "explorer";
}) {
  const raw =
    document.markdown ??
    document.content ??
    citation.source_text ??
    citation.excerpt ??
    citation.snippet ??
    "";
  const blocks = useMemo(() => parseMarkdown(raw), [raw]);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const target = useMemo(() => {
    if (mode !== "chat") return "";
    return (
      citation.source_text ?? citation.excerpt ?? citation.snippet ?? citation.provision_id ?? ""
    );
  }, [citation, mode]);

  useEffect(() => {
    if (!target || !contentRef.current) return;
    const needle = target.trim().toLowerCase();
    const match = Array.from(
      contentRef.current.querySelectorAll<HTMLElement>("[data-source-text]"),
    ).find((node) => node.dataset.sourceText?.toLowerCase().includes(needle));
    match?.scrollIntoView({ block: "center" });
  }, [target, blocks]);

  const matches = query.trim().toLowerCase();
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
      <div className="markdown-viewer__toolbar">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Tìm trong văn bản"
          aria-label="Tìm trong văn bản"
        />
        <button type="button" onClick={() => void copy()}>
          {copied ? "Đã sao chép" : "Sao chép nguồn"}
        </button>
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
  return markdown
    .replace(/\r\n?/g, "\n")
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
