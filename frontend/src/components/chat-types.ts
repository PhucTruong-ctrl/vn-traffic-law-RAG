import type { Citation } from "./CitationCard";

export type Claim = {
  claim: string;
  claim_type?: string;
  provision_ids?: string[];
  case_id?: string;
};
export type ChatResponse =
  | {
      status: "VERIFIED";
      answer: string;
      claims: Claim[];
      citations: Citation[];
      disclaimer?: string;
      progress_events?: Array<Record<string, unknown>>;
      trace_id?: string;
      conversation_id?: string;
    }
  | {
      status: "ABSTAINED";
      abstention: { reason?: string; reason_code?: string };
      disclaimer?: string;
      progress_events?: Array<Record<string, unknown>>;
      trace_id?: string;
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
