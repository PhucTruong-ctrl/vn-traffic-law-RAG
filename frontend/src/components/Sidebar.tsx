import { useEffect, useRef, useState } from "react";
import { BookIcon, PanelIcon, PlusIcon, SearchIcon } from "./Icons";
import LegalMark from "./LegalMark";

type SidebarProps = {
  activeQuestion: string;
  onNewChat: () => void;
  onCollapsedChange?: (collapsed: boolean) => void;
};
export default function Sidebar({
  activeQuestion,
  onNewChat,
  onCollapsedChange,
}: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const wasMobileOpen = useRef(false);
  useEffect(() => {
    if (!mobileOpen) {
      if (wasMobileOpen.current) mobileToggleRef.current?.focus();
      wasMobileOpen.current = false;
      return;
    }
    wasMobileOpen.current = true;
    const sidebar = sidebarRef.current;
    const focusable = sidebar?.querySelector<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        return;
      }
      if (event.key !== "Tab" || !sidebar) return;
      const items = Array.from(
        sidebar.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [mobileOpen]);
  const closeMobile = () => setMobileOpen(false);
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
      <aside
        ref={sidebarRef}
        id="conversation-sidebar"
        className={`sidebar${mobileOpen ? " is-mobile-open" : ""}${collapsed ? " is-collapsed" : ""}`}
        aria-label="Lịch sử trò chuyện"
      >
        <div className="sidebar-head">
          <a className="wordmark" href="#" aria-label="Trợ lý Luật Giao thông">
            <LegalMark /> <span>Luật Giao thông</span>
          </a>
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
              const nextCollapsed = !collapsed;
              setCollapsed(nextCollapsed);
              onCollapsedChange?.(nextCollapsed);
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
            <SearchIcon />
            <span>Tìm kiếm</span>
          </span>
          <span className="sidebar-nav__item">
            <BookIcon />
            <span>Nguồn pháp luật</span>
          </span>
        </nav>
        <div className="chat-list">
          <p>Gần đây</p>
          <button type="button" className="active" onClick={closeMobile}>
            {activeQuestion || "Cuộc trò chuyện mới"}
          </button>
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
