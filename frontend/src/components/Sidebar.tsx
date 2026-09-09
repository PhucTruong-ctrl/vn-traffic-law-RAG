import { useEffect, useState } from "react";
import { BookIcon, PanelIcon, PlusIcon, SearchIcon } from "./Icons";
import LegalMark from "./LegalMark";

type SidebarProps = {
  activeQuestion: string;
  suggestions: string[];
  onNewChat: () => void;
  onSuggestion: (question: string) => void;
};

export default function Sidebar({
  activeQuestion,
  suggestions,
  onNewChat,
  onSuggestion,
}: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    if (!mobileOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [mobileOpen]);
  const closeMobile = () => setMobileOpen(false);
  return (
    <>
      <button
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
        id="conversation-sidebar"
        className={`sidebar${mobileOpen ? " is-mobile-open" : ""}`}
        aria-label="Lịch sử trò chuyện"
        aria-hidden={!mobileOpen}
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
