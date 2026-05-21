"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Database, MessagesSquare, RefreshCcw, Search, Settings, Stethoscope } from "lucide-react";
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
  const messages = useChatStore((state) => state.messages);
  const clearMessages = useChatStore((state) => state.clearMessages);
  const { sendMessage } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <main className="flex h-screen flex-col">
      <header className="border-b border-slate-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-clinic text-white">
              <Stethoscope className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-950">AcneLLM</h1>
              <p className="text-xs text-slate-500">Local dermatology assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <nav className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
              <TabButton active={activeTab === "chat"} onClick={() => setActiveTab("chat")} label="Chat">
                <MessagesSquare className="h-4 w-4" />
              </TabButton>
              <TabButton active={activeTab === "kb"} onClick={() => setActiveTab("kb")} label="KB">
                <Database className="h-4 w-4" />
              </TabButton>
              <TabButton active={activeTab === "settings"} onClick={() => setActiveTab("settings")} label="Settings">
                <Settings className="h-4 w-4" />
              </TabButton>
            </nav>
            <button
              type="button"
              onClick={clearMessages}
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 transition hover:bg-slate-50 hover:text-clinic"
              aria-label="Xóa hội thoại"
            >
              <RefreshCcw className="h-4 w-4" />
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
                        className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-sm text-slate-700 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-900"
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
              <MessageInput />
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
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-9 min-w-9 items-center justify-center rounded-md px-2 text-sm transition ${
        active ? "bg-white text-clinic shadow-sm" : "text-slate-500 hover:text-slate-900"
      }`}
      title={label}
      aria-label={label}
    >
      {children}
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
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-clinic text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            aria-label="Tìm kiếm"
          >
            <Search className="h-5 w-5" />
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
                <span>score {item.score.toFixed(4)}</span>
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
          <span className="font-medium">Chat mode</span>
          <select
            value={settings.mode}
            onChange={(event) => setSettings({ mode: event.target.value as typeof settings.mode })}
            className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
          >
            <option value="auto">Auto</option>
            <option value="hybrid">Hybrid</option>
            <option value="llm_only">LLM only</option>
          </select>
        </label>
        <label className="block space-y-2 text-sm text-slate-700">
          <span className="font-medium">KB top K: {settings.topK}</span>
          <input
            type="range"
            min={1}
            max={12}
            value={settings.topK}
            onChange={(event) => setSettings({ topK: Number(event.target.value) })}
            className="w-full accent-teal-700"
          />
        </label>
        <label className="block space-y-2 text-sm text-slate-700">
          <span className="font-medium">Temperature: {settings.temperature.toFixed(1)}</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={settings.temperature}
            onChange={(event) => setSettings({ temperature: Number(event.target.value) })}
            className="w-full accent-teal-700"
          />
        </label>
      </div>
    </section>
  );
}
