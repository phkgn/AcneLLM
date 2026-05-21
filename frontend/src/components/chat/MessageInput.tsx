"use client";

import { FormEvent, useState } from "react";
import { SendHorizontal } from "lucide-react";
import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/chatStore";

export function MessageInput() {
  const [input, setInput] = useState("");
  const { sendMessage } = useSSE();
  const isLoading = useChatStore((state) => state.isLoading);
  const mode = useChatStore((state) => state.settings.mode);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || isLoading) return;
    setInput("");
    sendMessage(message, mode);
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Mô tả tình trạng da mụn..."
          className="min-h-12 flex-1 rounded-lg border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none transition focus:border-clinic focus:ring-2 focus:ring-teal-100"
          disabled={isLoading}
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-clinic text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          aria-label="Gửi"
        >
          <SendHorizontal className="h-5 w-5" />
        </button>
      </div>
      <div className="text-xs text-slate-500">Mode: {mode}</div>
    </form>
  );
}
