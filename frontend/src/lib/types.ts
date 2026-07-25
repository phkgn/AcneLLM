export interface RetrievedSource {
  chunk_id: string;
  source: string;
  title: string;
  url?: string;
  score: number;
  text: string;
}

export type EvidenceQuality = "strong" | "moderate" | "weak" | "unverified";

export type FeedbackRating = "up" | "down";

export interface DoneData {
  mode: string;
  latency_ms: number;
  used_chunks: string[];
  session_id?: string;
  evidence_quality?: EvidenceQuality;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: RetrievedSource[];
  mode?: string;
  latency_ms?: number;
  evidence_quality?: EvidenceQuality;
  isStreaming?: boolean;
  error?: string;
  feedback?: FeedbackRating | null;
}

export interface StreamEvent {
  event: "token" | "source" | "done" | "error";
  data: string | RetrievedSource | DoneData;
}

export interface KBSearchResult {
  chunk_id: string;
  source: string;
  text: string;
  score: number;
}

export interface ChatSettings {
  mode: "auto" | "hybrid" | "llm_only";
  temperature: number;
  topK: number;
}
