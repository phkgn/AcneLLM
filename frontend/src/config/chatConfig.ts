import type { ChatSettings } from "@/lib/types";

// ============================================================
// chatConfig.ts — Tất cả params frontend có thể tuning
// Backend params -> chỉnh trong .env.baseline (root project)
// ============================================================

// ── API connection ───────────────────────────────────────────
// Override bằng NEXT_PUBLIC_API_URL trong .env.local
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── UI ────────────────────────────────────────────────────────
export const CHAT_INPUT_ID = "chat-message-input";

// ── Chat defaults ─────────────────────────────────────────────
// Các giá trị này là default khi user chưa chỉnh trong Settings tab.
// Tất cả đều truyền thực sự xuống backend qua query params.
export const DEFAULT_CHAT_SETTINGS: ChatSettings = {
  // -> query param "mode" | backend: chat.py `mode: str = "auto"` | HOAT DONG
  mode: "auto",

  // -> query param "temperature" | backend: ollama stream_text | HOAT DONG
  // LLM_TEMPERATURE trong .env.baseline là server-side default,
  // giá trị này override per-request từ UI
  temperature: 0.2,

  // -> POST /api/v1/kb/search body "top_k" | KB Explorer only | HOAT DONG
  // Khong anh huong chat stream (RAG top_k duoc config bang CHAT_RERANK_TOP_K trong .env)
  topK: 5,
};

// ── Param ranges (dùng cho slider trong Settings tab) ─────────
export const TEMPERATURE_RANGE = { min: 0, max: 1, step: 0.1 };
export const KB_TOP_K_RANGE = { min: 1, max: 12 };
