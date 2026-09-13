"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "./Sidebar";

export default function PageShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <main className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <Sidebar
        activeQuestion=""
        onNewChat={() => router.push("/chat")}
        onSelectConversation={(id) => router.push(`/chat/${encodeURIComponent(id)}`)}
        onCollapsedChange={setSidebarCollapsed}
      />
      <section className="main-panel" aria-label="Nội dung ứng dụng">
        {children}
      </section>
    </main>
  );
}
