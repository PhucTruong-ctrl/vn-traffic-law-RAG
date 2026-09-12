"use client";

import { createPortal } from "react-dom";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, MoreHorizontal, PanelLeft, Plus, Search } from "lucide-react";
import Link from "next/link";
import LegalMark from "./LegalMark";
import Modal from "./Modal";
import type { Conversation } from "./chat-types";
import { createClient } from "../../utils/supabase/client";
import { apiUrl } from "../lib/api";
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
  const supabase = useMemo(() => createClient(), []);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  useEffect(() => {
    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setUserEmail(data.session?.user.email ?? null);
      setAccessToken(data.session?.access_token ?? null);
      setAuthReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      setUserEmail(session?.user.email ?? null);
      setAccessToken(session?.access_token ?? null);
      setAuthReady(true);
    });
    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, [supabase]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [actionMenu, setActionMenu] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const wasMobileOpen = useRef(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const [title, setTitle] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLSpanElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [userMenuPosition, setUserMenuPosition] = useState({ top: 0, left: 0 });
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const userMenuRef = useRef<HTMLSpanElement>(null);
  const userMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const fetchConversations = useCallback(
    async (nextCursor?: string | null, query = search) => {
      if (!authReady || !accessToken) {
        setConversationsLoading(false);
        return;
      }
      const isLoadingMore = Boolean(nextCursor);
      if (isLoadingMore) setLoadingMore(true);
      else setConversationsLoading(true);
      const params = new URLSearchParams({ limit: "30" });
      if (query.trim()) params.set("search", query.trim());
      if (nextCursor) params.set("cursor", nextCursor);
      try {
        const result = await fetch(apiUrl(`chats?${params}`), {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (result.status === 401) {
          await supabase.auth.signOut();
          return;
        }
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
        // Keep already loaded sessions usable when another page fails.
      } finally {
        setConversationsLoading(false);
        setLoadingMore(false);
      }
    },
    [authReady, accessToken, search],
  );
  useEffect(() => {
    const sentinel = loadMoreRef.current;
    const scrollRoot = sentinel?.closest<HTMLElement>(".chat-list__scroll");
    if (!sentinel || !scrollRoot || !cursor || loadingMore || search.trim()) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && cursor && !loadingMore) void fetchConversations(cursor);
      },
      { root: scrollRoot, rootMargin: "0px 0px 240px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [cursor, fetchConversations, loadingMore, search]);
  useEffect(() => {
    const activity = onConversationActivity;
    if (!activity) return;
    const refresh = window.setTimeout(() => void fetchConversations(), 0);
    return () => window.clearTimeout(refresh);
  }, [fetchConversations, onConversationActivity]);
  useEffect(() => {
    if (!authReady) return;
    const timer = window.setTimeout(() => void fetchConversations(), 0);
    return () => window.clearTimeout(timer);
  }, [authReady, accessToken, fetchConversations]);

  useEffect(() => {
    if (!searchOpen || !authReady || !accessToken) return;
    const timer = window.setTimeout(() => {
      setCursor(null);
      void fetchConversations(null, search);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search, searchOpen, authReady, accessToken, fetchConversations]);

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
        menuTriggerRef.current?.focus();
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
  const updateUserMenuPosition = () => {
    const trigger = userMenuTriggerRef.current;
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
      rect.top - menuHeight - gutter >= gutter ? rect.top - menuHeight - 4 : rect.bottom + 4;
    setUserMenuPosition({ top, left });
  };

  useEffect(() => {
    if (!userMenuOpen) return;
    updateUserMenuPosition();
    const reposition = () => updateUserMenuPosition();
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !userMenuTriggerRef.current?.contains(target) &&
        !userMenuRef.current?.contains(target)
      ) {
        setUserMenuOpen(false);
        userMenuTriggerRef.current?.focus();
      }
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
    };
  }, [userMenuOpen]);

  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError("");
    setPasswordMessage("");
    if (newPassword.length < 8) {
      setPasswordError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordError("Mật khẩu xác nhận không khớp.");
      return;
    }
    const result = await supabase.auth.updateUser({ password: newPassword });
    if (result.error) setPasswordError(result.error.message);
    else {
      setNewPassword("");
      setConfirmNewPassword("");
      setPasswordMessage("Đổi mật khẩu thành công.");
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    setUserMenuOpen(false);
  }

  async function rename(id: string) {
    if (!authReady || !accessToken) return;
    const next = title.trim();
    if (!next) return;
    const result = await fetch(apiUrl(`chats/${encodeURIComponent(id)}`), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
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
    if (!authReady || !accessToken) return;
    const result = await fetch(apiUrl(`chats/${encodeURIComponent(id)}`), {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (result.ok) {
      setConversations((items) => items.filter((item) => item.id !== id));
      setDeleteTarget(null);
    }
  }

  const closeMobile = () => setMobileOpen(false);
  const closeUserMenu = () => {
    setUserMenuOpen(false);
    userMenuTriggerRef.current?.focus();
  };
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
        aria-label="Mở điều hướng"
        aria-controls="conversation-sidebar"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
      >
        <PanelLeft aria-hidden="true" />
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
          <Search />
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
            <Search />
          </button>
          <button
            type="button"
            className="icon-button sidebar-close-mobile"
            aria-label="Đóng điều hướng"
            onClick={closeMobile}
          >
            <PanelLeft />
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
            <PanelLeft />
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
          <Plus />
          <span>Cuộc trò chuyện mới</span>
        </button>
        <nav className="sidebar-nav" aria-label="Điều hướng">
          <Link className="sidebar-nav__item" href="/legal-sources" onClick={closeMobile}>
            <BookOpen />
            <span>Nguồn pháp luật</span>
          </Link>
          <Link className="sidebar-nav__item" href="/saved" onClick={closeMobile}>
            <BookOpen />
            <span>Đã lưu</span>
          </Link>
        </nav>
        <div className="chat-list">
          <div className="chat-list__scroll">
            <p>Gần đây</p>
            {conversationsLoading && !conversations.length
              ? Array.from({ length: 5 }, (_, index) => (
                  <span
                    key={`history-skeleton-${index}`}
                    className="chat-list__skeleton"
                    aria-hidden="true"
                  />
                ))
              : conversations.map((item, index) => (
                  <div
                    key={item.id}
                    className={`chat-list__item sidebar-enter__item${item.id === activeConversationId ? " active" : ""}`}
                    style={{ "--sidebar-delay": `${Math.min(index, 11) * 45}ms` } as CSSProperties}
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
                          title={`Tùy chọn ${item.title}`}
                          aria-haspopup="menu"
                          aria-expanded={actionMenu === item.id}
                          aria-controls={`chat-menu-${item.id}`}
                          onClick={(event) => {
                            if (actionMenu === item.id) {
                              setActionMenu(null);
                              event.currentTarget.focus();
                              return;
                            }
                            menuTriggerRef.current = event.currentTarget;
                            setActionMenu(item.id);
                          }}
                        >
                          <MoreHorizontal aria-hidden="true" />
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
                              setDeleteTarget(item);
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
            {loadingMore &&
              Array.from({ length: 3 }, (_, index) => (
                <span
                  key={`history-more-skeleton-${index}`}
                  className="chat-list__skeleton"
                  aria-hidden="true"
                />
              ))}
            {cursor && !search.trim() && (
              <div ref={loadMoreRef} className="chat-list__load-sentinel" aria-hidden="true" />
            )}
            {cursor && search.trim() && (
              <button type="button" onClick={() => void fetchConversations(cursor)}>
                Tải thêm
              </button>
            )}
          </div>
        </div>
        <div className="sidebar-user">
          <span className="user-avatar" aria-hidden="true">
            ND
          </span>
          <span className="sidebar-user__identity">
            <b title={userEmail ?? undefined}>{userEmail?.split("@", 1)[0] ?? "Người dùng"}</b>
            <small>Trợ lý pháp luật</small>
          </span>
          <button
            ref={userMenuTriggerRef}
            type="button"
            className="sidebar-user__menu"
            aria-label="Mở tùy chọn tài khoản"
            title="Mở tùy chọn tài khoản"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            aria-controls="account-menu"
            onClick={() => setUserMenuOpen((open) => !open)}
          >
            <MoreHorizontal aria-hidden="true" />
          </button>
          {userMenuOpen &&
            typeof document !== "undefined" &&
            createPortal(
              <span
                id="account-menu"
                ref={userMenuRef}
                className="chat-list__menu sidebar-user__popover"
                role="menu"
                aria-label="Tùy chọn tài khoản"
                style={{ top: userMenuPosition.top, left: userMenuPosition.left }}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setPasswordError("");
                    setPasswordMessage("");
                    setPasswordOpen(true);
                    closeUserMenu();
                  }}
                >
                  Đổi mật khẩu
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    void signOut();
                    closeUserMenu();
                  }}
                >
                  Đăng xuất
                </button>
              </span>,
              document.body,
            )}
        </div>
        <Modal
          open={passwordOpen}
          onClose={() => setPasswordOpen(false)}
          label="Đổi mật khẩu"
          className="account-dialog"
        >
          <form className="account-dialog__form" onSubmit={(event) => void changePassword(event)}>
            <h2>Đổi mật khẩu</h2>
            <label>
              Mật khẩu mới
              <input
                type="password"
                minLength={8}
                required
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <label>
              Nhập lại mật khẩu mới
              <input
                type="password"
                minLength={8}
                required
                value={confirmNewPassword}
                onChange={(event) => setConfirmNewPassword(event.target.value)}
              />
            </label>
            {passwordError && <p role="alert">{passwordError}</p>}
            {passwordMessage && <p className="account-dialog__success">{passwordMessage}</p>}
            <button type="submit">Lưu mật khẩu</button>
          </form>
        </Modal>
        <Modal
          open={Boolean(deleteTarget)}
          onClose={() => setDeleteTarget(null)}
          label="Xác nhận xóa cuộc trò chuyện"
          className="account-dialog"
        >
          <div className="account-dialog__form">
            <h2>Xóa cuộc trò chuyện?</h2>
            <p>
              Bạn có chắc muốn xóa “{deleteTarget?.title || "Cuộc trò chuyện"}” không? Hành động này
              không thể hoàn tác.
            </p>
            <div>
              <button type="button" onClick={() => setDeleteTarget(null)}>
                Hủy
              </button>
              <button
                type="button"
                onClick={() => {
                  if (deleteTarget) void remove(deleteTarget.id);
                }}
              >
                Xóa
              </button>
            </div>
          </div>
        </Modal>
      </aside>
    </>
  );
}
