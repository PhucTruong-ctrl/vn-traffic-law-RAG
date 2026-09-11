"use client";

import { usePathname } from "next/navigation";
import ChatPage from "../../src/components/ChatPage";

export default function ChatLayout() {
  const pathname = usePathname();
  const conversationId = pathname.startsWith("/chat/")
    ? decodeURIComponent(pathname.slice("/chat/".length).split("/")[0])
    : undefined;
  return <ChatPage key={conversationId ?? "new"} conversationId={conversationId} />;
}
