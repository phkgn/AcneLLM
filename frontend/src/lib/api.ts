import type { KBSearchResult } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function createStreamUrl(message: string, sessionId: string, mode = "auto"): string {
  const params = new URLSearchParams({ message, session_id: sessionId, mode });
  return `${API_URL}/api/v1/chat/stream?${params.toString()}`;
}

export async function searchKB(query: string, topK: number): Promise<KBSearchResult[]> {
  const response = await fetch(`${API_URL}/api/v1/kb/search`, {
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
