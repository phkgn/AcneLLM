"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { CHAT_INPUT_ID } from "@/config/chatConfig";
import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/chatStore";

export function MessageInput({ autoFocusTrigger }: { autoFocusTrigger?: unknown }) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage } = useSSE();
  const isLoading = useChatStore((state) => state.isLoading);
  const settings = useChatStore((state) => state.settings);

  // Mode thực tế của tin nhắn cuối (từ done event backend)
  const messages = useChatStore((state) => state.messages);
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant" && !m.isStreaming);
  const lastActualMode = lastAssistant?.mode;

  const focusInput = () => {
    inputRef.current?.focus({ preventScroll: true });
  };

  // Focus khi mount lần đầu
  useEffect(() => {
    focusInput();
  }, []);

  // Focus lại khi bot trả lời xong
  useEffect(() => {
    if (!isLoading) {
      focusInput();
    }
  }, [isLoading]);

  // Focus lại khi tab chat được active
  useEffect(() => {
    focusInput();
  }, [autoFocusTrigger]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const message = input.trim();
    if (!message || isLoading) return;
    setInput("");
    sendMessage(message, settings.mode);
    requestAnimationFrame(focusInput);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (!isLoading) {
      submit();
    }
  };

  const MAX_WORDS = 500;
  const wordCount = input.trim() ? input.trim().split(/\s+/).length : 0;
  const overLimit = wordCount > MAX_WORDS;
  const canSend = input.trim().length > 0 && !isLoading && !overLimit;

  // Label mode: ưu tiên mode thực tế từ done event, fallback về setting
  const modeLabel = lastActualMode ?? settings.mode;
  const modeDisplay: Record<string, string> = {
    hybrid: "Hybrid (RAG + LLM)",
    llm_only: "LLM only",
    auto: "Tự động",
    clarify: "Cần thêm thông tin",
    refuse: "Ngoài phạm vi",
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex items-end gap-2">
        <textarea
          id={CHAT_INPUT_ID}
          ref={inputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isLoading ? "Đang trả lời... (vẫn có thể soạn tiếp)" : "Mô tả tình trạng da mụn..."}
          rows={1}
          className="max-h-36 min-h-12 flex-1 resize-none rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm leading-6 text-slate-900 outline-none transition focus:border-clinic focus:ring-2 focus:ring-teal-100"
          autoComplete="off"
          aria-label="Tin nhắn chat"
          aria-busy={isLoading}
        />
        <button
          type="submit"
          disabled={!canSend}
          className="h-12 shrink-0 rounded-lg bg-clinic px-4 text-sm font-medium text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          aria-label={isLoading ? "Đang trả lời..." : "Gửi"}
          title={isLoading ? "Đang trả lời..." : !input.trim() ? "Nhập tin nhắn trước" : "Gửi (Enter)"}
        >
          {isLoading ? "..." : "Gửi"}
        </button>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>
          {isLoading ? (
            <span className="text-teal-600">Đang tạo phản hồi — Enter tạm thời bị chặn, Shift+Enter để xuống dòng</span>
          ) : (
            <span>Enter để gửi · Shift+Enter xuống dòng</span>
          )}
        </span>
        <span className="flex items-center gap-3">
          {wordCount > 400 && (
            <span className={overLimit ? "text-red-500 font-medium" : "text-amber-500"}>
              {wordCount}/{MAX_WORDS} từ{overLimit ? " — quá giới hạn" : ""}
            </span>
          )}
          <span title="Chế độ thực tế của lượt cuối (từ backend)">
            {modeDisplay[modeLabel] ?? modeLabel}
          </span>
        </span>
      </div>
    </form>
  );
}
