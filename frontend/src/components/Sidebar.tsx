"use client";

import { createPortal } from "react-dom";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BookIcon, PanelIcon, PlusIcon, SearchIcon } from "./Icons";
import LegalMark from "./LegalMark";
import Modal from "./Modal";
import type { Conversation } from "./chat-types";

type ConversationActivity = { id: string; nonce: number } | null;

type SidebarProps = {
  activeConversationId?: string;
  activeQuestion: string;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onCollapsedChange?: (collapsed: boolean) => void;
  onConversationActivity?: ConversationActivity;
};

export default function Sidebar({
  activeConversationId,
  activeQuestion,
  onNewChat,
  onSelectConversation,
  onCollapsedChange,
  onConversationActivity,
}: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [actionMenu, setActionMenu] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLSpanElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const wasMobileOpen = useRef(false);

  async function fetchConversations(nextCursor?: string | null) {
    const params = new URLSearchParams({ limit: "30" });
    if (search.trim()) params.set("search", search.trim());
    if (nextCursor) params.set("cursor", nextCursor);
    try {
      const result = await fetch(`/api/v1/conversations?${params}`);
      if (!result.ok) return;
      const payload = (await result.json()) as {
        conversations?: Conversation[];
        items?: Conversation[];
        next_cursor?: string | null;
        cursor?: string | null;
      };
      const items = payload.conversations ?? payload.items ?? [];
      setConversations((previous) => (nextCursor ? [...previous, ...items] : items));
      setCursor(payload.next_cursor ?? payload.cursor ?? null);
    } catch {
      // History remains non-blocking when API is unavailable.
    }
  }
  const [animatingConversationId, setAnimatingConversationId] = useState<string | null>(null);
  const animationTimerRef = useRef<number | null>(null);
  const initialAnimationIdsRef = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (initialAnimationIdsRef.current !== null || !conversations.length) return;
    initialAnimationIdsRef.current = new Set(conversations.map((item) => item.id));
  }, [conversations]);
  useEffect(() => {
    const activity = onConversationActivity;
    if (!activity) return;
    const reorder = window.setTimeout(() => {
      setConversations((items) => {
        const index = items.findIndex((item) => item.id === activity.id);
        if (index <= 0) return items;
        const item = items[index];
        return [item, ...items.slice(0, index), ...items.slice(index + 1)];
      });
      setAnimatingConversationId(activity.id);
      if (animationTimerRef.current !== null) {
        window.clearTimeout(animationTimerRef.current);
      }
      animationTimerRef.current = window.setTimeout(() => {
        setAnimatingConversationId(null);
        animationTimerRef.current = null;
      }, 320);
    }, 0);
    return () => window.clearTimeout(reorder);
  }, [onConversationActivity]);
  useEffect(() => {
    const timer = window.setTimeout(() => void fetchConversations(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!mobileOpen) {
      if (wasMobileOpen.current) mobileToggleRef.current?.focus();
      wasMobileOpen.current = false;
      return;
    }
    wasMobileOpen.current = true;
    const sidebar = sidebarRef.current;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", close);
    sidebar
      ?.querySelector<HTMLElement>(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
      )
      ?.focus();
    return () => document.removeEventListener("keydown", close);
  }, [mobileOpen]);

  const cancelRename = () => {
    setEditing(null);
    setTitle("");
  };

  useEffect(() => {
    if (!editing) return;
    const cancelOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && !renameInputRef.current?.contains(target)) {
        cancelRename();
      }
    };
    const cancelOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        cancelRename();
      }
    };
    document.addEventListener("pointerdown", cancelOnOutsidePointer);
    document.addEventListener("keydown", cancelOnEscape);
    return () => {
      document.removeEventListener("pointerdown", cancelOnOutsidePointer);
      document.removeEventListener("keydown", cancelOnEscape);
    };
  }, [editing]);
  const updateMenuPosition = () => {
    const trigger = menuTriggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 132;
    const menuHeight = 90;
    const gutter = 8;
    const left = Math.min(
      Math.max(gutter, rect.right - menuWidth),
      window.innerWidth - menuWidth - gutter,
    );
    const top =
      rect.bottom + menuHeight + gutter <= window.innerHeight
        ? rect.bottom + 4
        : Math.max(gutter, rect.top - menuHeight - 4);
    setMenuPosition({ top, left });
  };

  useEffect(() => {
    if (!actionMenu) return;
    updateMenuPosition();
    const reposition = () => updateMenuPosition();
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !menuTriggerRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setActionMenu(null);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActionMenu(null);
        menuTriggerRef.current?.focus();
      }
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [actionMenu]);

  async function rename(id: string) {
    const next = title.trim();
    if (!next) return;
    const result = await fetch(`/api/v1/conversations/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: next }),
    });
    if (result.ok) {
      setConversations((items) =>
        items.map((item) => (item.id === id ? { ...item, title: next } : item)),
      );
      setEditing(null);
      setTitle("");
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Xóa cuộc trò chuyện này?")) return;
    const result = await fetch(`/api/v1/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (result.ok) setConversations((items) => items.filter((item) => item.id !== id));
  }

  const closeMobile = () => setMobileOpen(false);
  const visibleConversations = search.trim()
    ? conversations.filter((item) =>
        item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
      )
    : conversations;

  return (
    <>
      <button
        ref={mobileToggleRef}
        type="button"
        className="mobile-sidebar-toggle"
        aria-controls="conversation-sidebar"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
      >
        <PanelIcon />
        <span>Mở điều hướng</span>
      </button>
      {mobileOpen && (
        <button
          type="button"
          className="mobile-sidebar-backdrop"
          aria-label="Đóng điều hướng"
          onClick={closeMobile}
        />
      )}
      <Modal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        label="Tìm kiếm cuộc trò chuyện"
        className="search-dialog"
      >
        <div className="search-dialog__input">
          <SearchIcon />
          <input
            autoFocus
            aria-label="Tìm kiếm"
            placeholder="Tìm kiếm..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <p className="search-dialog__heading">Cuộc trò chuyện gần đây</p>
        <div className="search-dialog__results">
          {visibleConversations.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => {
                onSelectConversation(item.id);
                setSearchOpen(false);
              }}
            >
              <span className="search-dialog__bubble" aria-hidden="true" />
              <span>{item.title}</span>
            </button>
          ))}
          {!visibleConversations.length && <p>Không tìm thấy cuộc trò chuyện.</p>}
        </div>
      </Modal>
      <aside
        ref={sidebarRef}
        id="conversation-sidebar"
        className={`sidebar${mobileOpen ? " is-mobile-open" : ""}${collapsed ? " is-collapsed" : ""}`}
        aria-label="Lịch sử trò chuyện"
      >
        <div
          className="sidebar-head sidebar-enter__item"
          style={{ "--sidebar-delay": "0ms" } as CSSProperties}
        >
          <Link className="wordmark" href="/chat" aria-label="Trợ lý Luật Giao thông">
            <LegalMark />
            <span>Luật Giao thông</span>
          </Link>
          <button
            type="button"
            className="icon-button sidebar-search-button"
            aria-label="Tìm kiếm cuộc trò chuyện"
            onClick={() => setSearchOpen(true)}
          >
            <SearchIcon />
          </button>
          <button
            type="button"
            className="icon-button sidebar-close-mobile"
            aria-label="Đóng điều hướng"
            onClick={closeMobile}
          >
            <PanelIcon />
          </button>
          <button
            type="button"
            className="icon-button sidebar-collapse-toggle"
            aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            aria-expanded={!collapsed}
            onClick={() => {
              const next = !collapsed;
              setCollapsed(next);
              onCollapsedChange?.(next);
            }}
          >
            <PanelIcon />
          </button>
        </div>
        <button
          type="button"
          className="new-chat"
          aria-label="Cuộc trò chuyện mới"
          onClick={() => {
            onNewChat();
            closeMobile();
          }}
        >
          <PlusIcon />
          <span>Cuộc trò chuyện mới</span>
        </button>
        <nav className="sidebar-nav" aria-label="Điều hướng">
          <span className="sidebar-nav__item">
            <BookIcon />
            <span>Nguồn pháp luật</span>
          </span>
        </nav>
        <div className="chat-list">
          <p>Gần đây</p>
          {conversations.map((item, index) => (
            <div
              key={item.id}
              className={`chat-list__item${
                initialAnimationIdsRef.current?.has(item.id) ? " sidebar-enter__item" : ""
              }${item.id === activeConversationId ? " active" : ""}${
                item.id === animatingConversationId ? " is-reordered" : ""
              }`}
              style={
                initialAnimationIdsRef.current?.has(item.id)
                  ? ({ "--sidebar-delay": `${Math.min(index, 11) * 45}ms` } as React.CSSProperties)
                  : undefined
              }
            >
              <button
                type="button"
                className={item.id === activeConversationId ? "active" : ""}
                onClick={() => {
                  onSelectConversation(item.id);
                  closeMobile();
                }}
              >
                {item.title || activeQuestion || "Cuộc trò chuyện"}
              </button>
              {editing === item.id ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void rename(item.id);
                  }}
                >
                  <input
                    ref={renameInputRef}
                    aria-label="Tên cuộc trò chuyện"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    autoFocus
                  />
                </form>
              ) : (
                <span className="chat-list__actions">
                  <button
                    ref={menuTriggerRef}
                    type="button"
                    className="chat-list__menu-trigger"
                    aria-label={`Tùy chọn ${item.title}`}
                    aria-expanded={actionMenu === item.id}
                    aria-controls={`chat-menu-${item.id}`}
                    onClick={(event) => {
                      if (actionMenu === item.id) {
                        setActionMenu(null);
                        return;
                      }
                      menuTriggerRef.current = event.currentTarget;
                      setActionMenu(item.id);
                    }}
                  >
                    <span aria-hidden="true">•••</span>
                  </button>
                </span>
              )}
              {actionMenu === item.id &&
                typeof document !== "undefined" &&
                createPortal(
                  <span
                    ref={menuRef}
                    id={`chat-menu-${item.id}`}
                    className="chat-list__menu"
                    role="menu"
                    style={{ top: menuPosition.top, left: menuPosition.left }}
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setEditing(item.id);
                        setTitle(item.title);
                        setActionMenu(null);
                      }}
                    >
                      Đổi tên
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        void remove(item.id);
                        setActionMenu(null);
                      }}
                    >
                      Xóa
                    </button>
                  </span>,
                  document.body,
                )}
            </div>
          ))}
          {cursor && (
            <button type="button" onClick={() => void fetchConversations(cursor)}>
              Tải thêm
            </button>
          )}
        </div>
        <div className="sidebar-user">
          <span className="user-avatar" aria-hidden="true">
            ND
          </span>
          <span>
            <b>Người dùng</b>
            <small>Trợ lý pháp luật</small>
          </span>
          <span className="sidebar-user__menu" aria-hidden="true">
            •••
          </span>
        </div>
      </aside>
    </>
  );
}
