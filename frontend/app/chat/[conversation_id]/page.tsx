import ChatPage from "../../../src/components/ChatPage";

export default async function ConversationRoute({ params }: { params: Promise<{ conversation_id: string }> }) {
  const { conversation_id: conversationId } = await params;
  return <ChatPage conversationId={conversationId} />;
}
