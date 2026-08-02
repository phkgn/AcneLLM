"use client";

import { useEffect, useRef } from "react";

export interface ChunkDetail {
  chunk_id: string;
  source: string;
  title?: string;
  url?: string;
  score?: number;
  text: string;
}

interface Props {
  chunk: ChunkDetail | null;
  onClose: () => void;
}

export function ChunkDetailModal({ chunk, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  /* Đóng khi nhấn Escape */
  useEffect(() => {
    if (!chunk) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [chunk, onClose]);

  /* Khoá scroll body khi modal mở */
  useEffect(() => {
    if (chunk) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [chunk]);

  if (!chunk) return null;

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === overlayRef.current) onClose();
  };

  const scoreColor =
    chunk.score === undefined
      ? ""
      : chunk.score >= 0.65
      ? "text-emerald-600"
      : chunk.score >= 0.4
      ? "text-amber-600"
      : "text-rose-500";

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Chi tiết chunk"
    >
      <div
        ref={dialogRef}
        className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-slate-200 bg-white shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm font-semibold text-slate-900 leading-snug">
              {chunk.title || chunk.source || chunk.chunk_id}
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">{chunk.chunk_id}</span>
              {chunk.source && <span>{chunk.source}</span>}
              {chunk.score !== undefined && (
                <span className={`font-medium ${scoreColor}`}>
                  điểm {chunk.score.toFixed(4)}
                </span>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {chunk.url && (
              <a
                href={chunk.url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700"
              >
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M6.5 3H3a1 1 0 00-1 1v9a1 1 0 001 1h9a1 1 0 001-1V9.5M9.5 2H14m0 0v4.5M14 2L7.5 8.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Nguồn
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="Đóng"
            >
              <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 3l10 10M13 3L3 13" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Body — full text, scrollable */}
        <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-4">
          <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{chunk.text}</p>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 px-5 py-3 text-right">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-200"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
