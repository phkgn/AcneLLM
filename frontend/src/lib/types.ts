export interface Citation {
  chunk_id: string;
  source: string;
  title: string;
  url?: string;
  score: number;
  text: string;
}

export interface DoneData {
  mode: string;
  latency_ms: number;
  used_chunks: string[];
  session_id?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  mode?: string;
  latency_ms?: number;
  isStreaming?: boolean;
  error?: string;
}

export interface StreamEvent {
  event: "token" | "citation" | "warning" | "done" | "error";
  data: string | Citation | DoneData | string[];
}

export interface KBSearchResult {
  chunk_id: string;
  source: string;
  text: string;
  score: number;
}

export interface ChatSettings {
  mode: "auto" | "hybrid" | "llm_only";
  topK: number;
  temperature: number;
}
