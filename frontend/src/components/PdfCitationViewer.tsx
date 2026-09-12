"use client";

import { ChevronLeft, ChevronRight, RefreshCw, ZoomIn, ZoomOut } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Citation } from "./CitationCard";

type ViewerState = "loading" | "ready" | "error";
type ZoomMode = "fit" | number;

export default function PdfCitationViewer({ citation }: { citation: Citation }) {
  const initialPage = citation.page == null ? 1 : Math.max(1, citation.page);
  const key = `${citation.document_id}:${citation.page ?? "none"}`;
  return <PdfCitationDocument key={key} citation={citation} initialPage={initialPage} />;
}

function PdfCitationDocument({
  citation,
  initialPage,
}: {
  citation: Citation;
  initialPage: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLSpanElement>(null);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [draftPage, setDraftPage] = useState(String(initialPage));
  const [pageCount, setPageCount] = useState(0);
  const [zoom, setZoom] = useState<ZoomMode>("fit");
  const [containerWidth, setContainerWidth] = useState(720);
  const [state, setState] = useState<ViewerState>(
    citation.document_id && citation.pdf_url ? "loading" : "error",
  );
  const [error, setError] = useState(
    citation.document_id && citation.pdf_url ? "" : "Trích dẫn này chưa có nguồn PDF để mở.",
  );
  const [retryToken, setRetryToken] = useState(0);
  const highlightStyle = useMemo(() => normalizeBbox(citation.bbox), [citation.bbox]);
  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const update = () => setContainerWidth(Math.max(280, element.clientWidth - 36));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!citation.document_id || !citation.pdf_url) return;
    let cancelled = false;
    let renderTask: { promise: Promise<void>; cancel: () => void } | undefined;
    let loadingTask: { promise: Promise<unknown>; destroy: () => Promise<void> } | undefined;
    const render = async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        if (cancelled) return;
        setState("loading");
        setError("");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
        loadingTask = pdfjs.getDocument({
          url: citation.pdf_url ?? citation.source_url ?? "",
          standardFontDataUrl: "/pdfjs/standard_fonts/",
          isImageDecoderSupported: false,
        }) as typeof loadingTask;
        const pdf = (await loadingTask!.promise) as import("pdfjs-dist").PDFDocumentProxy;
        if (cancelled) return;
        setPageCount(pdf.numPages);
        const safePage = Math.min(Math.max(1, pageNumber), pdf.numPages);
        if (safePage !== pageNumber) setPageNumber(safePage);
        setDraftPage(String(safePage));
        const page = await pdf.getPage(safePage);
        if (cancelled || !canvasRef.current) return;
        const unit = page.getViewport({ scale: 1 });
        const scale = zoom === "fit" ? Math.max(0.25, containerWidth / unit.width) : zoom;
        const viewport = page.getViewport({ scale });
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const canvas = canvasRef.current;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("Trình duyệt không hỗ trợ hiển thị PDF.");
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        await renderTask.promise;
        if (cancelled) return;
        setState("ready");
        requestAnimationFrame(() =>
          highlightRef.current?.scrollIntoView({
            block: "center",
            inline: "center",
          }),
        );
      } catch (caught) {
        if (!cancelled && (caught as { name?: string }).name !== "RenderingCancelledException") {
          setState("error");
          setError(caught instanceof Error ? caught.message : "Không thể tải bản PDF chính thức.");
        }
      }
    };
    void render();
    return () => {
      cancelled = true;
      renderTask?.cancel();
      void loadingTask?.destroy();
    };
  }, [citation.document_id, citation.pdf_url, containerWidth, pageNumber, zoom, retryToken]);
  const zoomLabel = zoom === "fit" ? "Vừa chiều rộng" : `${Math.round(zoom * 100)}%`;
  const changeZoom = (delta: number) =>
    setZoom((value) => Math.min(3, Math.max(0.5, (value === "fit" ? 1 : value) + delta)));
  const commitPage = () => {
    const next = Math.max(
      1,
      Math.min(pageCount || Number.MAX_SAFE_INTEGER, Number(draftPage) || 1),
    );
    setDraftPage(String(next));
    setPageNumber(next);
  };
  return (
    <section
      className="pdf-viewer"
      aria-label={`Bản PDF, trang ${pageNumber}`}
      aria-busy={state === "loading"}
    >
      <div className="pdf-viewer__toolbar">
        <div className="pdf-viewer__pages" aria-label="Điều hướng trang">
          <button
            type="button"
            onClick={() => setPageNumber((page) => Math.max(1, page - 1))}
            disabled={pageNumber <= 1}
            aria-label="Trang trước"
            title="Trang trước"
          >
            <ChevronLeft aria-hidden="true" />
          </button>
          <label htmlFor="pdf-page-number">
            Trang{" "}
            <input
              id="pdf-page-number"
              type="number"
              min={1}
              max={pageCount || undefined}
              value={draftPage}
              onChange={(event) => setDraftPage(event.target.value)}
              onBlur={commitPage}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitPage();
                }
              }}
            />
          </label>
          <span>/ {pageCount || "—"}</span>
          <button
            type="button"
            onClick={() => setPageNumber((page) => Math.min(pageCount || page + 1, page + 1))}
            disabled={!pageCount || pageNumber >= pageCount}
            aria-label="Trang sau"
            title="Trang sau"
          >
            <ChevronRight aria-hidden="true" />
          </button>
        </div>
        <div className="pdf-viewer__zoom">
          <button
            type="button"
            onClick={() => changeZoom(-0.1)}
            aria-label="Thu nhỏ"
            title="Thu nhỏ"
          >
            <ZoomOut aria-hidden="true" />
          </button>
          <span>{zoomLabel}</span>
          <button
            type="button"
            onClick={() => changeZoom(0.1)}
            aria-label="Phóng to"
            title="Phóng to"
          >
            <ZoomIn aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setZoom("fit")}
            aria-label="Vừa chiều rộng"
            title="Vừa chiều rộng"
          >
            Vừa chiều rộng
          </button>
        </div>
      </div>
      <div ref={viewportRef} className="pdf-viewer__viewport">
        {state === "loading" && (
          <div className="pdf-viewer__status" role="status">
            Đang tải bản PDF chính thức…
          </div>
        )}
        {state === "error" && (
          <div className="pdf-viewer__error" role="alert">
            <strong>Không mở được PDF</strong>
            <span>{error || "Nguồn PDF không khả dụng."}</span>
            <button
              type="button"
              onClick={() => setRetryToken((token) => token + 1)}
              aria-label="Thử lại"
              title="Thử lại"
            >
              <RefreshCw aria-hidden="true" />
              <span>Thử lại</span>
            </button>
            {citation.source_url && (
              <a href={citation.source_url} target="_blank" rel="noreferrer">
                Mở tại nguồn chính thức ↗
              </a>
            )}
          </div>
        )}
        <div className="pdf-viewer__page" hidden={state === "error"}>
          <canvas ref={canvasRef} />
          {highlightStyle && state === "ready" && (
            <span
              ref={highlightRef}
              className="pdf-viewer__highlight"
              style={highlightStyle}
              role="mark"
              aria-label="Đoạn trích dẫn được đánh dấu"
            />
          )}
        </div>
      </div>
      <div className="pdf-viewer__caption">
        {highlightStyle
          ? "Vùng màu vàng là đoạn được trích dẫn."
          : "Trích dẫn chưa có tọa độ OCR; đang hiển thị đúng trang nguồn."}
      </div>
    </section>
  );
}
function normalizeBbox(bbox: Citation["bbox"]): CSSProperties | undefined {
  if (!bbox) return undefined;
  const values = Array.isArray(bbox) ? bbox : [bbox.left, bbox.top, bbox.right, bbox.bottom];
  if (
    values.length !== 4 ||
    values.some((value) => !Number.isFinite(value) || value < 0 || value > 1)
  )
    return undefined;
  const [left, top, right, bottom] = values;
  if (right <= left || bottom <= top) return undefined;
  return {
    position: "absolute",
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${(right - left) * 100}%`,
    height: `${(bottom - top) * 100}%`,
  };
}
