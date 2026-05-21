"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { CHAT_INPUT_ID, KB_TOP_K_RANGE, TEMPERATURE_RANGE } from "@/config/chatConfig";
import { searchKB } from "@/lib/api";
import type { KBSearchResult } from "@/lib/types";
import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/chatStore";
import { MessageBubble } from "./MessageBubble";
import { MessageInput } from "./MessageInput";

const SUGGESTIONS = [
  "Em 22 tuổi, da dầu, mụn viêm ở cằm 4 tuần, đang dùng BHA.",
  "Mụn ẩn hai bên má nên chăm sóc thế nào?",
  "Đang mang thai có dùng retinol trị mụn được không?",
];

export function ChatWindow() {
  const [activeTab, setActiveTab] = useState<"chat" | "kb" | "settings">("chat");
  const [chatFocusTick, setChatFocusTick] = useState(0);
  const messages = useChatStore((state) => state.messages);
  const isLoading = useChatStore((state) => state.isLoading);
  const clearMessages = useChatStore((state) => state.clearMessages);
  const { sendMessage } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const switchToChat = () => {
    setActiveTab("chat");
    setChatFocusTick((t) => t + 1);
  };

  const focusChatInput = (event: MouseEvent<HTMLElement>) => {
    if (activeTab !== "chat") return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.closest("button,a,input,textarea,select,[role='button']")) return;
    document.getElementById(CHAT_INPUT_ID)?.focus({ preventScroll: true });
  };

  return (
    <main className="flex h-screen flex-col" onMouseDown={focusChatInput}>
      <header className="border-b border-slate-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-clinic text-white font-bold text-sm select-none">
              Ac
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-950">AcneLLM</h1>
              <p className="text-xs text-slate-500">Tư vấn da mụn nội bộ</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <nav className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
              <TabButton active={activeTab === "chat"} onClick={switchToChat} label="Chat" />
              <TabButton active={activeTab === "kb"} onClick={() => setActiveTab("kb")} label="KB" />
              <TabButton active={activeTab === "settings"} onClick={() => setActiveTab("settings")} label="Cài đặt" />
            </nav>
            <button
              type="button"
              onClick={clearMessages}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-clinic"
              aria-label="Xóa hội thoại"
            >
              Xóa
            </button>
          </div>
        </div>
      </header>

      {activeTab === "chat" ? (
        <>
          <section className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto max-w-5xl space-y-5">
              {messages.length === 0 ? (
                <div className="mx-auto max-w-3xl rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="mb-4 text-sm font-medium text-slate-700">Gợi ý nhanh</div>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => sendMessage(suggestion)}
                        disabled={isLoading}
                        className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-sm text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-900 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              <div ref={bottomRef} />
            </div>
          </section>

          <footer className="border-t border-slate-200 bg-white/90 px-4 py-4 backdrop-blur">
            <div className="mx-auto max-w-3xl">
              <MessageInput autoFocusTrigger={chatFocusTick} />
              <p className="mt-2 text-center text-xs text-slate-500">
                Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán từ bác sĩ.
              </p>
            </div>
          </footer>
        </>
      ) : activeTab === "kb" ? (
        <KBExplorer />
      ) : (
        <SettingsPanel />
      )}
    </main>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-9 rounded-md px-3 text-sm transition ${
        active ? "bg-white text-clinic shadow-sm font-medium" : "text-slate-500 hover:text-slate-900"
      }`}
      aria-label={label}
    >
      {label}
    </button>
  );
}

function KBExplorer() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KBSearchResult[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const topK = useChatStore((state) => state.settings.topK);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      setResults(await searchKB(query.trim(), topK));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tìm kiếm KB.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm trong knowledge base..."
            className="min-h-12 flex-1 rounded-lg border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none transition focus:border-clinic focus:ring-2 focus:ring-teal-100"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="h-12 shrink-0 rounded-lg bg-clinic px-4 text-sm font-medium text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? "Đang tìm..." : "Tìm kiếm"}
          </button>
        </form>
        {error ? <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}
        {loading ? <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">Đang tìm...</div> : null}
        <div className="space-y-3">
          {results.map((item) => (
            <article key={item.chunk_id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span className="font-mono">{item.chunk_id}</span>
                <span>{item.source}</span>
                <span>điểm {item.score.toFixed(4)}</span>
              </div>
              <p className="text-sm leading-6 text-slate-700">{item.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function SettingsPanel() {
  const settings = useChatStore((state) => state.settings);
  const setSettings = useChatStore((state) => state.setSettings);

  return (
    <section className="flex-1 px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-5 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <label className="block space-y-2 text-sm text-slate-700">
          <span className="font-medium">Chế độ chat</span>
          <p className="text-xs text-slate-400">
            Truyền vào backend qua query param mode. Auto = backend tự chọn pipeline phù hợp.
          </p>
          <select
            value={settings.mode}
            onChange={(event) => setSettings({ mode: event.target.value as typeof settings.mode })}
            className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
          >
            <option value="auto">Tự động (để backend quyết định)</option>
            <option value="hybrid">Hybrid (RAG + LLM)</option>
            <option value="llm_only">LLM only (không RAG)</option>
          </select>
        </label>

        <label className="block space-y-2 text-sm text-slate-700">
          <span className="font-medium">Nhiệt độ (chat): {settings.temperature.toFixed(1)}</span>
          <p className="text-xs text-slate-400">
            Mức ngẫu nhiên của câu trả lời. 0.0 = chắc chắn, 1.0 = sáng tạo hơn. Truyền qua query param temperature.
          </p>
          <input
            type="range"
            min={TEMPERATURE_RANGE.min}
            max={TEMPERATURE_RANGE.max}
            step={TEMPERATURE_RANGE.step}
            value={settings.temperature}
            onChange={(event) => setSettings({ temperature: Number(event.target.value) })}
            className="w-full accent-teal-700"
          />
        </label>

        <label className="block space-y-2 text-sm text-slate-700">
          <span className="font-medium">KB top K (KB Explorer): {settings.topK}</span>
          <p className="text-xs text-slate-400">
            Số chunk trả về khi tìm kiếm thủ công trong tab KB. Không ảnh hưởng đến chat stream.
          </p>
          <input
            type="range"
            min={KB_TOP_K_RANGE.min}
            max={KB_TOP_K_RANGE.max}
            value={settings.topK}
            onChange={(event) => setSettings({ topK: Number(event.target.value) })}
            className="w-full accent-teal-700"
          />
        </label>
      </div>
    </section>
  );
}
