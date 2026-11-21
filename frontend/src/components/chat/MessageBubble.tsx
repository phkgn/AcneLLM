"use client";

import { useState } from "react";
import type { ChatMessage, EvidenceQuality, FeedbackRating } from "@/lib/types";
import { submitFeedback } from "@/lib/api";
import { useChatStore } from "@/stores/chatStore";
import { SourceCard } from "./SourceCard";

const EVIDENCE_CONFIG: Record<EvidenceQuality, { label: string; className: string }> = {
  strong:     { label: "Bang chung tot",  className: "border-green-200 bg-green-50 text-green-700" },
  moderate:   { label: "Bang chung vua",  className: "border-amber-200 bg-amber-50 text-amber-700" },
  weak:       { label: "Bang chung yeu",  className: "border-rose-200 bg-rose-50 text-rose-700" },
  unverified: { label: "LLM only",        className: "border-slate-200 bg-slate-50 text-slate-500" },
};

// ── Feedback bar ──────────────────────────────────────────────────────────────
function FeedbackBar({ message }: { message: ChatMessage }) {
  const [sending, setSending] = useState(false);
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);
  const sessionId           = useChatStore((s) => s.sessionId);
  const current             = message.feedback;

  const vote = async (rating: FeedbackRating) => {
    if (current === rating || sending) return;
    setSending(true);
    try {
      await submitFeedback(message.id, rating, sessionId);
      setMessageFeedback(message.id, rating);
    } catch {
      // silent fail
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5 mt-1">
      <span className="text-xs text-slate-400">Huu ich?</span>
      <ThumbButton direction="up"   active={current === "up"}   disabled={sending || current != null} onClick={() => void vote("up")} />
      <ThumbButton direction="down" active={current === "down"} disabled={sending || current != null} onClick={() => void vote("down")} />
      {current != null ? (
        <span className="ml-0.5 text-xs text-slate-400">
          {current === "up" ? "Cam on! 👍" : "Cam on, se cai thien."}
        </span>
      ) : null}
    </div>
  );
}

function ThumbButton({
  direction, active, disabled, onClick,
}: {
  direction: "up" | "down";
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const isUp        = direction === "up";
  const activeClass = isUp
    ? "border-emerald-300 bg-emerald-50 text-emerald-600"
    : "border-rose-300 bg-rose-50 text-rose-500";
  const idleClass   = "border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-600";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={isUp ? "Huu ich" : "Khong huu ich"}
      aria-pressed={active}
      className={`flex h-7 w-7 items-center justify-center rounded-md border transition ${active ? activeClass : idleClass} disabled:cursor-default`}
    >
      {isUp ? (
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M18 9.5a1.5 1.5 0 11-3 0v-6a1.5 1.5 0 013 0v6zM14 9.667v-5.43a2 2 0 00-1.106-1.79l-.05-.025A4 4 0 0011.057 2H5.641a2 2 0 00-1.962 1.608l-1.2 6A2 2 0 004.44 12H8v4a2 2 0 002 2 1 1 0 001-1v-.667a4 4 0 01.8-2.4l1.4-1.866a4 4 0 00.8-2.4z" />
        </svg>
      )}
    </button>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────────────────
export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser       = message.role === "user";
  const showFeedback =
    !isUser && !message.isStreaming && !message.error &&
    message.mode !== "clarify" && message.mode !== "refuse";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-clinic text-white font-bold text-xs select-none">
          AI
        </div>
      ) : null}

      <div className={`max-w-[82%] space-y-2 ${isUser ? "items-end" : "items-start"}`}>
        {/* Bubble */}
        <div
          className={`rounded-lg px-4 py-3 shadow-sm ${
            isUser
              ? "bg-ink text-white"
              : message.error
                ? "border border-rose-200 bg-rose-50 text-rose-900"
                : "border border-slate-200 bg-white text-slate-800"
          }`}
        >
          {message.isStreaming && !message.content ? (
            <div className="space-y-2">
              <div className="h-3 w-56 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-36 animate-pulse rounded bg-slate-200" />
            </div>
          ) : (
            <div className="whitespace-pre-wrap text-sm leading-6">{message.content}</div>
          )}
        </div>

        {/* Nguồn tài liệu */}
        {!isUser && message.sources && message.sources.length > 0 ? (
          <div className="space-y-2">
            {message.sources.map((source, index) => (
              <SourceCard
                key={`${source.chunk_id}-${index}`}
                source={source}
                index={index + 1}
              />
            ))}
          </div>
        ) : null}

        {/* Mode / evidence / latency + feedback */}
        {!isUser && !message.isStreaming && (message.mode || message.latency_ms !== undefined) ? (
          <div className="space-y-1.5">
            <div className="flex flex-wrap gap-2 text-xs text-slate-400">
              {message.mode ? (
                <span
                  className={`rounded-md border px-2 py-1 font-medium ${
                    message.mode === "hybrid"    ? "border-teal-200 bg-teal-50 text-teal-700"   :
                    message.mode === "llm_only"  ? "border-slate-200 bg-slate-50 text-slate-600" :
                    message.mode === "clarify"   ? "border-amber-200 bg-amber-50 text-amber-700" :
                    message.mode === "refuse"    ? "border-rose-200 bg-rose-50 text-rose-600"    :
                                                   "border-slate-200 bg-white text-slate-500"
                  }`}
                >
                  {message.mode === "hybrid"   ? "Hybrid (RAG + LLM)" :
                   message.mode === "llm_only" ? "LLM only"           :
                   message.mode === "clarify"  ? "Can them thong tin" :
                   message.mode === "refuse"   ? "Ngoai pham vi"      :
                   message.mode}
                </span>
              ) : null}

              {message.evidence_quality ? (
                <span
                  className={`rounded-md border px-2 py-1 font-medium ${
                    EVIDENCE_CONFIG[message.evidence_quality]?.className ?? "border-slate-200 bg-white text-slate-500"
                  }`}
                  title="Muc do tin cay dua tren chat luong nguon tham khao tu knowledge base"
                >
                  {EVIDENCE_CONFIG[message.evidence_quality]?.label ?? message.evidence_quality}
                </span>
              ) : null}

              {message.latency_ms !== undefined ? (
                <span className="rounded-md border border-slate-200 bg-white px-2 py-1">
                  {message.latency_ms}ms
                </span>
              ) : null}
            </div>

            {showFeedback ? <FeedbackBar message={message} /> : null}
          </div>
        ) : null}
      </div>

      {isUser ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blush text-white font-bold text-xs select-none">
          B
        </div>
      ) : null}
    </div>
  );
}
