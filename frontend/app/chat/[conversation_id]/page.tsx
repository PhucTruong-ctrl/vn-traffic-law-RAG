import ChatPage from "../../../src/components/ChatPage";

type ConversationRouteProps = {
  params: Promise<{ conversation_id: string }>;
};

export default async function ConversationRoute({ params }: ConversationRouteProps) {
  const { conversation_id: rawConversationId } = await params;
  const conversationId = decodeURIComponent(rawConversationId).trim();

  if (!conversationId) {
    return <ChatPage />;
  }

  return <ChatPage conversationId={conversationId} />;
}
