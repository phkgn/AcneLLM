"use client";

import { useCallback } from "react";
import { createStreamUrl } from "@/lib/api";
import type { Citation, DoneData, StreamEvent } from "@/lib/types";
import { useChatStore } from "@/stores/chatStore";

export function useSSE() {
  const sessionId = useChatStore((state) => state.sessionId);
  const isLoading = useChatStore((state) => state.isLoading);
  const selectedMode = useChatStore((state) => state.settings.mode);
  const temperature = useChatStore((state) => state.settings.temperature);
  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const addAssistantPlaceholder = useChatStore((state) => state.addAssistantPlaceholder);
  const appendToLastAssistant = useChatStore((state) => state.appendToLastAssistant);
  const addCitationToLastAssistant = useChatStore((state) => state.addCitationToLastAssistant);
  const finishLastAssistant = useChatStore((state) => state.finishLastAssistant);
  const failLastAssistant = useChatStore((state) => state.failLastAssistant);
  const setLoading = useChatStore((state) => state.setLoading);

  const sendMessage = useCallback(
    async (message: string, mode = selectedMode) => {
      const clean = message.trim();
      if (!clean || isLoading) return;

      addUserMessage(clean);
      addAssistantPlaceholder();
      setLoading(true);

      try {
        const response = await fetch(createStreamUrl(clean, sessionId, mode, temperature));
        if (!response.ok || !response.body) {
          throw new Error(`Backend returned ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";

          for (const frame of frames) {
            const line = frame.split("\n").find((item) => item.startsWith("data: "));
            if (!line) continue;

            const event = JSON.parse(line.slice(6)) as StreamEvent;
            if (event.event === "token" && typeof event.data === "string") {
              appendToLastAssistant(event.data);
            } else if (event.event === "citation") {
              addCitationToLastAssistant(event.data as Citation);
            } else if (event.event === "error" && typeof event.data === "string") {
              failLastAssistant(event.data);
            } else if (event.event === "done") {
              finishLastAssistant(event.data as DoneData);
            }
          }
        }
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : "Không thể kết nối backend.";
        failLastAssistant(errMsg);
      } finally {
        setLoading(false);
      }
    },
    [
      addAssistantPlaceholder,
      addCitationToLastAssistant,
      addUserMessage,
      appendToLastAssistant,
      failLastAssistant,
      finishLastAssistant,
      isLoading,
      sessionId,
      selectedMode,
      setLoading,
      temperature,
    ],
  );

  return { sendMessage };
}
