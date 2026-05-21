import { Bot, UserRound } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { CitationCard } from "./CitationCard";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-clinic text-white">
          <Bot className="h-5 w-5" />
        </div>
      ) : null}

      <div className={`max-w-[82%] space-y-2 ${isUser ? "items-end" : "items-start"}`}>
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

        {!isUser && message.citations && message.citations.length > 0 ? (
          <div className="space-y-2">
            {message.citations.map((citation, index) => (
              <CitationCard key={`${citation.chunk_id}-${index}`} citation={citation} index={index + 1} />
            ))}
          </div>
        ) : null}

        {!isUser && !message.isStreaming && (message.mode || message.latency_ms !== undefined) ? (
          <div className="flex flex-wrap gap-2 text-xs text-slate-500">
            {message.mode ? (
              <span className="rounded-md border border-slate-200 bg-white px-2 py-1">
                {message.mode}
              </span>
            ) : null}
            {message.latency_ms !== undefined ? (
              <span className="rounded-md border border-slate-200 bg-white px-2 py-1">
                {message.latency_ms}ms
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {isUser ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blush text-white">
          <UserRound className="h-5 w-5" />
        </div>
      ) : null}
    </div>
  );
}
