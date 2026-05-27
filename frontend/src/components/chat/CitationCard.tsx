"use client";

import { useState } from "react";
import type { Citation } from "@/lib/types";
import { ChunkDetailModal } from "./ChunkDetailModal";
import type { ChunkDetail } from "./ChunkDetailModal";

type SourceType =
  | "nice_guideline"
  | "aad_guideline"
  | "jid_paper"
  | "pubmed_review"
  | "clinical_textbook"
  | "vi_medical_site"
  | "forum_post"
  | "blog"
  | "unknown";

const SOURCE_BADGE: Record<SourceType, { label: string; className: string }> = {
  nice_guideline:    { label: "NICE Guideline",  className: "bg-emerald-100 text-emerald-800 border-emerald-200" },
  aad_guideline:    { label: "AAD Guideline",   className: "bg-blue-100 text-blue-800 border-blue-200" },
  jid_paper:        { label: "JID Paper",       className: "bg-violet-100 text-violet-800 border-violet-200" },
  pubmed_review:    { label: "PubMed Review",   className: "bg-indigo-100 text-indigo-800 border-indigo-200" },
  clinical_textbook:{ label: "Textbook",        className: "bg-amber-100 text-amber-800 border-amber-200" },
  vi_medical_site:  { label: "Y te VN",         className: "bg-teal-100 text-teal-800 border-teal-200" },
  forum_post:       { label: "Forum",           className: "bg-slate-100 text-slate-600 border-slate-200" },
  blog:             { label: "Blog",            className: "bg-slate-100 text-slate-500 border-slate-200" },
  unknown:          { label: "KB",              className: "bg-slate-100 text-slate-500 border-slate-200" },
};

function inferSourceType(citation: Citation): SourceType {
  const meta = (citation as unknown as { metadata?: Record<string, string> }).metadata;
  if (meta?.source_type && meta.source_type in SOURCE_BADGE) {
    return meta.source_type as SourceType;
  }
  const src = (citation.source || "").toLowerCase();
  const url = (citation.url || "").toLowerCase();
  if (src.includes("nice") || url.includes("nice.org")) return "nice_guideline";
  if (src.includes("aad")  || url.includes("aad.org"))  return "aad_guideline";
  if (src.includes("jid")  || url.includes("jidonline")) return "jid_paper";
  if (url.includes("pubmed") || url.includes("ncbi.nlm")) return "pubmed_review";
  if (src.includes("textbook")) return "clinical_textbook";
  if (url.includes(".vn") || src.includes("vinmec") || src.includes("medlatec")) return "vi_medical_site";
  if (src.includes("forum") || src.includes("reddit")) return "forum_post";
  if (src.includes("blog")) return "blog";
  return "unknown";
}

function ScoreBar({ score }: { score: number }) {
  const pct   = Math.min(100, Math.round(score * 100));
  const color = score >= 0.65 ? "bg-emerald-400" : score >= 0.40 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-1.5" title={`Diem lien quan: ${score.toFixed(3)}`}>
      <div className="h-1.5 w-14 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400">{score.toFixed(2)}</span>
    </div>
  );
}

export function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const [modalChunk, setModalChunk] = useState<ChunkDetail | null>(null);
  const sourceType   = inferSourceType(citation);
  const badge        = SOURCE_BADGE[sourceType];
  const displayTitle = citation.title || citation.source || citation.chunk_id;

  const openModal = () => {
    setModalChunk({
      chunk_id: citation.chunk_id,
      source: citation.source,
      title: citation.title,
      url: citation.url,
      score: citation.score,
      text: citation.text,
    });
  };

  return (
    <>
      <div
        onClick={openModal}
        className="group cursor-pointer rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden transition hover:border-teal-300 hover:shadow-md"
        title="Click để xem toàn bộ nội dung chunk"
      >
        {/* Header row */}
        <div className="flex items-start gap-2 px-3 pt-3 pb-2">
          {/* Index */}
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-slate-100 text-xs font-bold text-slate-500">
            {index}
          </span>

          {/* Title + badge */}
          <div className="min-w-0 flex-1 space-y-1.5">
            <p className="text-sm font-medium leading-snug text-slate-900 line-clamp-2 group-hover:text-teal-700 transition">
              {displayTitle}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-semibold ${badge.className}`}>
                {badge.label}
              </span>
              <ScoreBar score={citation.score} />
            </div>
          </div>

          {/* Actions */}
          <div className="ml-1 flex shrink-0 items-center gap-1.5">
            {/* View detail hint */}
            <span className="hidden group-hover:inline-flex items-center gap-1 text-xs font-medium text-teal-600">
              <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" strokeLinecap="round" strokeLinejoin="round"/>
                <circle cx="8" cy="8" r="2"/>
              </svg>
              Chi tiết
            </span>

            {/* Source link */}
            {citation.url ? (
              <a
                href={citation.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700"
                aria-label={`Mo nguon: ${displayTitle}`}
                onClick={(e) => e.stopPropagation()}
              >
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M6.5 3H3a1 1 0 00-1 1v9a1 1 0 001 1h9a1 1 0 001-1V9.5M9.5 2H14m0 0v4.5M14 2L7.5 8.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Nguon
              </a>
            ) : null}
          </div>
        </div>

        {/* Text excerpt — always clipped to 2 lines; full text visible in modal */}
        <div className="px-3 pb-3">
          <p className="line-clamp-2 text-sm leading-relaxed text-slate-600">
            {citation.text}
          </p>
          {citation.text && citation.text.length > 150 ? (
            <span className="mt-1 block text-xs font-medium text-teal-600">
              Xem toàn bộ →
            </span>
          ) : null}
        </div>
      </div>

      <ChunkDetailModal chunk={modalChunk} onClose={() => setModalChunk(null)} />
    </>
  );
}
