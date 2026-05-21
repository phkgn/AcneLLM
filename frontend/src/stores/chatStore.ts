"use client";

import { create } from "zustand";
import type { ChatMessage, ChatSettings, Citation, DoneData } from "@/lib/types";

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function findLastAssistant(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "assistant") return i;
  }
  return -1;
}

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string;
  isLoading: boolean;
  settings: ChatSettings;
  addMessage: (message: ChatMessage) => void;
  addUserMessage: (content: string) => void;
  addAssistantPlaceholder: () => void;
  appendToLastAssistant: (token: string) => void;
  addCitationToLastAssistant: (citation: Citation) => void;
  finishLastAssistant: (data: DoneData) => void;
  failLastAssistant: (message: string) => void;
  setLoading: (value: boolean) => void;
  setSettings: (settings: Partial<ChatSettings>) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: makeId(),
  isLoading: false,
  settings: { mode: "auto", topK: 5, temperature: 0.3 },

  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),

  addUserMessage: (content) =>
    set((state) => ({
      messages: [...state.messages, { id: makeId(), role: "user", content }],
    })),

  addAssistantPlaceholder: () =>
    set((state) => ({
      messages: [
        ...state.messages,
        { id: makeId(), role: "assistant", content: "", isStreaming: true },
      ],
    })),

  appendToLastAssistant: (token) =>
    set((state) => {
      const messages = [...state.messages];
      const index = findLastAssistant(messages);
      if (index >= 0) {
        messages[index] = {
          ...messages[index],
          content: messages[index].content + token,
        };
      }
      return { messages };
    }),

  addCitationToLastAssistant: (citation) =>
    set((state) => {
      const messages = [...state.messages];
      const index = findLastAssistant(messages);
      if (index >= 0) {
        const citations = messages[index].citations || [];
        messages[index] = { ...messages[index], citations: [...citations, citation] };
      }
      return { messages };
    }),

  finishLastAssistant: (data) =>
    set((state) => {
      const messages = [...state.messages];
      const index = findLastAssistant(messages);
      if (index >= 0) {
        messages[index] = {
          ...messages[index],
          isStreaming: false,
          mode: data.mode,
          latency_ms: data.latency_ms,
        };
      }
      return { messages };
    }),

  failLastAssistant: (message) =>
    set((state) => {
      const messages = [...state.messages];
      const index = findLastAssistant(messages);
      if (index >= 0) {
        messages[index] = {
          ...messages[index],
          content: messages[index].content || message,
          error: message,
          isStreaming: false,
        };
      }
      return { messages };
    }),

  setLoading: (value) => set({ isLoading: value }),

  setSettings: (settings) =>
    set((state) => ({ settings: { ...state.settings, ...settings } })),

  clearMessages: () => set({ messages: [], sessionId: makeId(), isLoading: false }),
}));
