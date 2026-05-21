import { ExternalLink } from "lucide-react";
import type { Citation } from "@/lib/types";

export function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm">
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium text-slate-900">
            [{index}] {citation.title || citation.source || citation.chunk_id}
          </div>
          <div className="text-xs text-slate-500">
            {citation.source || "KB"} · score {citation.score.toFixed(3)}
          </div>
        </div>
        {citation.url ? (
          <a
            href={citation.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-clinic"
            aria-label="Mở nguồn"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        ) : null}
      </div>
      <p className="line-clamp-3 text-slate-600">{citation.text}</p>
      <code className="mt-2 block break-all rounded bg-slate-50 px-2 py-1 text-xs text-slate-500">
        {citation.chunk_id}
      </code>
    </div>
  );
}
