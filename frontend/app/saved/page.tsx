"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "../../utils/supabase/client";
import { MarkdownAnswer } from "../../src/components/ChatThread";
import CitationCard, { type Citation } from "../../src/components/CitationCard";
import SourceDrawer from "../../src/components/SourceDrawer";
import Modal from "../../src/components/Modal";
import { apiUrl } from "../../src/lib/api";

type SavedItem = {
  id: string;
  assistant_message_id: string;
  source_session_id?: string | null;
  question: string;
  answer: string;
  citations: Citation[];
  response?: unknown;
  created_at?: string | null;
};

function citation(value: unknown): Citation | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (typeof item.source_id !== "string" || typeof item.document_id !== "string") return null;
  return {
    ...item,
    excerpt: typeof item.excerpt === "string" ? item.excerpt : "",
  } as Citation;
}

function normalize(payload: unknown): SavedItem[] {
  const values = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  const items = Array.isArray(payload)
    ? payload
    : (values.items ?? values.saved ?? values.results ?? values.data);
  if (!Array.isArray(items)) return [];
  return items.flatMap((value) => {
    if (!value || typeof value !== "object") return [];
    const item = value as Record<string, unknown>;
    const id = typeof item.id === "string" ? item.id : "";
    const assistantMessageId =
      typeof item.assistant_message_id === "string" ? item.assistant_message_id : "";
    const question = typeof item.question === "string" ? item.question : "";
    const answer = typeof item.answer === "string" ? item.answer : "";
    const citations = Array.isArray(item.citations)
      ? item.citations.flatMap((value) => {
          const normalized = citation(value);
          return normalized ? [normalized] : [];
        })
      : [];
    return id && assistantMessageId
      ? [
          {
            ...item,
            id,
            assistant_message_id: assistantMessageId,
            question,
            answer,
            citations,
          } as SavedItem,
        ]
      : [];
  });
}

export default function SavedPage() {
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const [items, setItems] = useState<SavedItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drawerCitation, setDrawerCitation] = useState<Citation | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SavedItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const { data } = await supabase.auth.getSession();
    if (!data.session) {
      router.push("/chat");
      return;
    }
    try {
      const response = await fetch(apiUrl("bookmarks"), {
        headers: { Authorization: `Bearer ${data.session.access_token}` },
      });
      if (!response.ok) throw new Error("Không thể tải danh sách đã lưu.");
      setItems(normalize(await response.json()));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tải danh sách đã lưu.");
    } finally {
      setLoading(false);
    }
  }, [router, supabase]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return term
      ? items.filter((item) =>
          [
            item.question,
            item.answer,
            ...item.citations.map((c) => c.excerpt || c.document_title || ""),
          ]
            .join(" ")
            .toLocaleLowerCase()
            .includes(term),
        )
      : items;
  }, [items, query]);
  async function remove(item: SavedItem) {
    if (deleting) return;
    setDeleting(true);
    setError("");
    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        router.push("/chat");
        return;
      }
      const response = await fetch(
        apiUrl(`bookmarks/${encodeURIComponent(item.assistant_message_id)}`),
        { method: "DELETE", headers: { Authorization: `Bearer ${data.session.access_token}` } },
      );
      if (response.ok) {
        setItems((current) =>
          current.filter((entry) => entry.assistant_message_id !== item.assistant_message_id),
        );
        setDeleteTarget(null);
      } else {
        setError("Không thể xóa mục đã lưu.");
      }
    } catch {
      setError("Không thể xóa mục đã lưu.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="legal-sources-page saved-page">
      <header className="legal-sources-page__header saved-page__header">
        <div>
          <Link href="/chat" className="legal-sources-page__back saved-page__back">
            ← Trợ lý
          </Link>
          <p className="eyebrow saved-page__eyebrow">THƯ VIỆN CÁ NHÂN</p>
          <div className="saved-page__title-row">
            <h1>Đã lưu</h1>
            {!loading && !error && <span className="saved-page__count">{items.length}</span>}
          </div>
          <p className="saved-page__intro">Các câu trả lời và trích dẫn bạn muốn xem lại.</p>
        </div>
      </header>
      <section className="legal-sources-page__filters saved-page__filters">
        <label htmlFor="saved-search">
          <span className="saved-page__search-label">Tìm kiếm</span>
          <span className="saved-page__search-wrap">
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
              <circle cx="11" cy="11" r="6.5" />
              <path d="m16 16 4 4" />
            </svg>
            <input
              id="saved-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm trong câu hỏi, câu trả lời hoặc nguồn"
            />
          </span>
        </label>
      </section>
      <section className="legal-sources-page__results saved-page__results" aria-live="polite">
        {loading && (
          <p className="legal-sources-page__state saved-page__state saved-page__state--loading">
            Đang tải mục đã lưu…
          </p>
        )}
        {!loading && error && (
          <div
            className="legal-sources-page__state saved-page__state saved-page__state--error"
            role="alert"
          >
            <p>{error}</p>
            <button type="button" onClick={() => void load()}>
              Thử lại
            </button>
          </div>
        )}
        {!loading && !error && !filtered.length && (
          <p className="legal-sources-page__state saved-page__state saved-page__state--empty">
            {items.length ? "Không tìm thấy mục phù hợp." : "Bạn chưa lưu câu trả lời nào."}
          </p>
        )}
        {!loading &&
          !error &&
          filtered.map((item) => (
            <article className="legal-source-card saved-card" key={item.id}>
              <div className="saved-card__header">
                <time dateTime={item.created_at ?? undefined}>
                  {item.created_at ? new Date(item.created_at).toLocaleString("vi-VN") : ""}
                </time>
                <button
                  className="saved-card__delete"
                  type="button"
                  onClick={() => setDeleteTarget(item)}
                  disabled={deleting}
                >
                  Xóa
                </button>
              </div>
              <button
                type="button"
                className="saved-card__question"
                onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                aria-expanded={expanded === item.id}
              >
                <strong>{item.question}</strong>
                <span>{expanded === item.id ? "Thu gọn ↑" : "Mở câu trả lời →"}</span>
              </button>
              {expanded === item.id && (
                <div className="saved-card__body">
                  <div className="saved-card__answer assistant-answer">
                    <MarkdownAnswer answer={item.answer} />
                  </div>
                  {item.source_session_id && (
                    <Link
                      className="saved-card__source"
                      href={`/chat/${encodeURIComponent(item.source_session_id)}`}
                    >
                      Mở cuộc trò chuyện gốc →
                    </Link>
                  )}
                  <div className="saved-card__citations">
                    {(item.citations || []).map((citation, index) => (
                      <CitationCard
                        key={`${citation.source_id}-${index}`}
                        citation={citation}
                        onOpenSource={setDrawerCitation}
                      />
                    ))}
                  </div>
                </div>
              )}
            </article>
          ))}
      </section>
      <SourceDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} />
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => {
          if (!deleting) setDeleteTarget(null);
        }}
        label="Xác nhận xóa mục đã lưu"
      >
        <div className="account-dialog__form">
          <h2>Xóa mục đã lưu?</h2>
          <p>Bạn có chắc muốn xóa câu trả lời này không? Hành động này không thể hoàn tác.</p>
          <div>
            <button type="button" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              Hủy
            </button>
            <button
              type="button"
              onClick={() => deleteTarget && void remove(deleteTarget)}
              disabled={deleting}
            >
              {deleting ? "Đang xóa…" : "Xóa"}
            </button>
          </div>
        </div>
      </Modal>
    </main>
  );
}
