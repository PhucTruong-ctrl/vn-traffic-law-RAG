import ChatPage from "../../../src/components/ChatPage";

export default function ConversationRoute({ params }: { params: { conversation_id: string } }) {
  return <ChatPage conversationId={decodeURIComponent(params.conversation_id)} />;
}
