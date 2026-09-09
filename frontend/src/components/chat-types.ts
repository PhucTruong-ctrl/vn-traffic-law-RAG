import type { Citation } from "./CitationCard";

export type Claim = {
  claim: string;
  claim_type?: string;
  provision_ids?: string[];
  case_id?: string;
};
export type ChatStatus =
  | "VERIFIED"
  | "GREETING"
  | "OUT_OF_SCOPE"
  | "CORPUS_NOT_COVERED"
  | "INSUFFICIENT_EVIDENCE"
  | "WORKFLOW_UNAVAILABLE";
export type ChatResponse = {
  status: ChatStatus;
  answer?: string | null;
  claims?: Claim[];
  citations?: Citation[];
  abstention?: { reason?: string; reason_code?: string; evidence_gaps?: string[] } | null;
  disclaimer?: string;
  progress_events?: Array<Record<string, unknown>>;
  trace_id?: string;
  assistant_message_id?: string;
  conversation_id?: string;
};
export type ConversationTurn = { question: string; response: ChatResponse };
export type Conversation = {
  id: string;
  title: string;
  last_activity_at?: string;
  created_at?: string;
  messages?: unknown[];
  turns?: ConversationTurn[];
};
