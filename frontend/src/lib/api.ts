import type { FeedbackRating, KBSearchResult } from "./types";
import { API_BASE_URL, DEFAULT_CHAT_SETTINGS } from "@/config/chatConfig";

export function createStreamUrl(
  message: string,
  sessionId: string,
  mode = DEFAULT_CHAT_SETTINGS.mode,
  temperature = DEFAULT_CHAT_SETTINGS.temperature,
): string {
  const params = new URLSearchParams({
    message,
    session_id: sessionId,
    mode,
    temperature: String(temperature),
  });
  return `${API_BASE_URL}/api/v1/chat/stream?${params.toString()}`;
}

export async function submitFeedback(
  messageId: string,
  rating: FeedbackRating,
  sessionId?: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_id: messageId, rating, session_id: sessionId ?? null }),
  });
  if (!response.ok) {
    throw new Error(`Feedback failed: ${response.status}`);
  }
}

export async function searchKB(query: string, topK: number): Promise<KBSearchResult[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/kb/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }
  const data = (await response.json()) as { results: KBSearchResult[] };
  return data.results || [];
}
