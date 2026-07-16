"use client";

import {
  Braces,
  ChevronLeft,
  ChevronRight,
  Columns2,
  FileSearch,
  RefreshCw,
  Search,
  Timer,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
  formatDuration,
  inputClass,
} from "./ui";

type JsonRecord = Record<string, unknown>;

type ListResponse = {
  experiment: string;
  system: string;
  dataset: string | null;
  availableSystems: string[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  rows: Array<{
    sampleId: string;
    query: string;
    ok: boolean;
    error: string | null;
    modelName: string | null;
    latencyMs: number | null;
    answerPreview: string;
    errorCodes: string[];
    flagged: boolean;
  }>;
};

type DetailResponse = {
  experiment: string;
  system: string;
  dataset: string | null;
  availableSystems: string[];
  result: JsonRecord | null;
  sample: JsonRecord | null;
  judged: JsonRecord | null;
  errorCodes: string[];
  compareSystem: string | null;
  compare: JsonRecord | null;
};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function InspectClient() {
  const [runs, setRuns] = useState<string[]>(["main_2x2_t3"]);
  const [experiment, setExperiment] = useState("main_2x2_t3");
  const [system, setSystem] = useState("s3");
  const [compareSystem, setCompareSystem] = useState("s1");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [list, setList] = useState<ListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/meta", { cache: "no-store" })
      .then((response) => response.json())
      .then((body: { reportRuns?: string[] }) => {
        setRuns(
          Array.from(new Set(["main_2x2_t3", ...(body.reportRuns ?? [])])),
        );
      });
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(queryInput);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [queryInput]);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        experiment,
        system,
        page: String(page),
      });
      if (query) params.set("query", query);
      const response = await fetch(`/api/inspect?${params}`, {
        cache: "no-store",
      });
      const body = (await response.json()) as ListResponse & { error?: string };
      if (!response.ok) throw new Error(body.error ?? "Không thể đọc results.");
      setList(body);
      if (body.availableSystems.length && !body.availableSystems.includes(system)) {
        setSystem(body.availableSystems[0]);
      }
      setSelectedId((current) => {
        if (current && body.rows.some((row) => row.sampleId === current)) {
          return current;
        }
        return body.rows[0]?.sampleId ?? null;
      });
    } catch (loadError) {
      setError((loadError as Error).message);
    } finally {
      setLoading(false);
    }
  }, [experiment, page, query, system]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    setDetail(null);
    if (!selectedId) return;
    const params = new URLSearchParams({
      experiment,
      system,
      sampleId: selectedId,
      compare: compareSystem,
    });
    void fetch(`/api/inspect?${params}`, { cache: "no-store" })
      .then((response) => response.json())
      .then((body: DetailResponse) => setDetail(body));
  }, [compareSystem, experiment, selectedId, system]);

  const availableSystems =
    list?.availableSystems.length
      ? list.availableSystems
      : ["s0", "s1", "s2", "s3", "s4"];
  const result = record(detail?.result);
  const trace = record(result.trace);
  const structured = result.structured;
  const judged = detail?.judged;
  const sample = record(detail?.sample);
  const compare = record(detail?.compare);

  return (
    <>
      <PageHeader
        eyebrow="Sample debugger"
        title="Inspect trace và diff từng câu"
        description="Tìm theo sample_id, câu hỏi hoặc answer; xem structured output, retrieval trace, judge score, error code và so sánh cùng sample giữa hai system."
        actions={
          <Button variant="ghost" onClick={() => void loadList()}>
            <RefreshCw size={16} />
            Refresh
          </Button>
        }
      />

      {error ? (
        <div className="mb-5 rounded-2xl border border-ember/20 bg-ember/10 px-4 py-3 text-sm font-bold text-ember">
          {error}
        </div>
      ) : null}

      <Card className="mb-5 p-4">
        <div className="grid gap-3 lg:grid-cols-[1fr_150px_150px_1.3fr]">
          <label className="text-xs font-black uppercase tracking-[0.1em] text-ink/45">
            Experiment
            <select
              value={experiment}
              onChange={(event) => {
                setExperiment(event.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className={`${inputClass} mt-1.5`}
            >
              {runs.map((run) => (
                <option key={run} value={run}>
                  {run}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-black uppercase tracking-[0.1em] text-ink/45">
            System
            <select
              value={system}
              onChange={(event) => {
                setSystem(event.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className={`${inputClass} mt-1.5`}
            >
              {availableSystems.map((item) => (
                <option key={item} value={item}>
                  {item.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-black uppercase tracking-[0.1em] text-ink/45">
            Diff with
            <select
              value={compareSystem}
              onChange={(event) => setCompareSystem(event.target.value)}
              className={`${inputClass} mt-1.5`}
            >
              {availableSystems
                .filter((item) => item !== system)
                .map((item) => (
                  <option key={item} value={item}>
                    {item.toUpperCase()}
                  </option>
                ))}
            </select>
          </label>
          <label className="text-xs font-black uppercase tracking-[0.1em] text-ink/45">
            Search
            <span className="relative mt-1.5 block">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35"
              />
              <input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="sample_id, question, answer…"
                className={`${inputClass} pl-9`}
              />
            </span>
          </label>
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[460px_minmax(0,1fr)]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <h2 className="font-black">Samples</h2>
              <p className="mt-0.5 text-xs text-ink/42">
                {list?.total ?? 0} rows · {list?.dataset ?? "dataset chưa xác định"}
              </p>
            </div>
            <Pill tone="neutral">50 / page</Pill>
          </div>
          <div className="max-h-[780px] divide-y divide-line overflow-y-auto">
            {list?.rows.map((row) => (
              <button
                key={row.sampleId}
                onClick={() => setSelectedId(row.sampleId)}
                className={`w-full px-5 py-4 text-left transition hover:bg-canvas/70 ${
                  selectedId === row.sampleId ? "bg-lime/15" : ""
                } ${row.flagged ? "border-l-4 border-l-ember" : "border-l-4 border-l-transparent"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-black">{row.sampleId}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-ink/58">
                      {row.query || row.answerPreview || "(không có text)"}
                    </p>
                  </div>
                  <Pill tone={row.ok ? "good" : "bad"}>{row.ok ? "OK" : "FAIL"}</Pill>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-bold text-ink/40">
                  <span className="flex items-center gap-1">
                    <Timer size={11} />
                    {formatDuration(row.latencyMs)}
                  </span>
                  {row.modelName ? <span>{row.modelName}</span> : null}
                  {row.errorCodes.slice(0, 2).map((code) => (
                    <span key={code} className="text-ember">
                      {code}
                    </span>
                  ))}
                </div>
              </button>
            ))}
            {!list?.rows.length ? (
              <div className="p-5">
                <EmptyState
                  title={loading ? "Đang đọc JSONL…" : "Không có sample"}
                  description="Run chưa tạo results.jsonl hoặc bộ lọc không khớp sample nào."
                />
              </div>
            ) : null}
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3">
            <button
              disabled={!list || list.page <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-white disabled:opacity-30"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs font-black text-ink/50">
              Page {list?.page ?? 1} / {list?.totalPages ?? 1}
            </span>
            <button
              disabled={!list || list.page >= list.totalPages}
              onClick={() => setPage((value) => value + 1)}
              className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-white disabled:opacity-30"
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </Card>

        <div className="min-w-0 space-y-5">
          {detail?.result ? (
            <>
              <Card className="p-5 sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Pill tone={result.ok === true ? "good" : "bad"}>
                        {result.ok === true ? "OK" : "FAIL"}
                      </Pill>
                      <Pill tone="info">{system.toUpperCase()}</Pill>
                      {detail.errorCodes.map((code) => (
                        <Pill key={code} tone="bad">
                          {code}
                        </Pill>
                      ))}
                    </div>
                    <h2 className="mt-3 text-xl font-black">
                      {String(sample.user_query ?? result.sample_id ?? "Sample")}
                    </h2>
                    <p className="mt-2 text-xs text-ink/45">
                      {String(result.sample_id)} · {String(result.model_name ?? "model —")} ·{" "}
                      {formatDuration(
                        typeof record(result.timings_ms).total === "number"
                          ? (record(result.timings_ms).total as number)
                          : null,
                      )}
                    </p>
                  </div>
                  {result.error ? (
                    <div className="flex max-w-lg gap-2 rounded-xl bg-ember/10 px-3 py-2 text-xs font-bold text-ember">
                      <TriangleAlert className="mt-0.5 shrink-0" size={14} />
                      {String(result.error)}
                    </div>
                  ) : null}
                </div>
                <div className="mt-5 rounded-2xl border border-line bg-white p-4">
                  <p className="text-xs font-black uppercase tracking-[0.12em] text-ink/40">
                    Answer
                  </p>
                  <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-ink/78">
                    {String(result.answer ?? "(rỗng)")}
                  </div>
                </div>
              </Card>

              <Card className="p-5 sm:p-6">
                <div className="flex items-center gap-2">
                  <Columns2 size={19} className="text-moss" />
                  <h2 className="text-xl font-black">
                    {system.toUpperCase()} vs {compareSystem.toUpperCase()}
                  </h2>
                </div>
                <div className="mt-5 grid gap-4 lg:grid-cols-2">
                  <AnswerPanel
                    label={system.toUpperCase()}
                    answer={String(result.answer ?? "(rỗng)")}
                    ok={result.ok === true}
                  />
                  <AnswerPanel
                    label={compareSystem.toUpperCase()}
                    answer={
                      detail.compare
                        ? String(compare.answer ?? "(rỗng)")
                        : "Không có record cùng sample_id ở system này."
                    }
                    ok={compare.ok === true}
                  />
                </div>
              </Card>

              <div className="grid gap-5 2xl:grid-cols-2">
                <Card className="p-5">
                  <div className="flex items-center gap-2">
                    <FileSearch size={18} className="text-moss" />
                    <h2 className="font-black">Trace</h2>
                  </div>
                  <div className="mt-4 space-y-3">
                    <TraceField label="query" value={trace.query} />
                    <TraceField
                      label="retrieved_ids"
                      value={trace.retrieved_ids}
                    />
                    <TraceField label="final_ids" value={trace.final_ids} />
                    <TraceField
                      label="normalized_user"
                      value={trace.normalized_user}
                    />
                    {!Object.keys(trace).length ? (
                      <p className="text-sm text-ink/45">Record không có trace.</p>
                    ) : null}
                    <details className="rounded-xl border border-line bg-white">
                      <summary className="cursor-pointer px-3 py-2.5 text-xs font-black uppercase tracking-[0.1em]">
                        Full trace JSON
                      </summary>
                      <pre className="max-h-96 overflow-auto border-t border-line p-3 text-[11px] leading-5">
                        {pretty(trace)}
                      </pre>
                    </details>
                  </div>
                </Card>

                <Card className="p-5">
                  <div className="flex items-center gap-2">
                    <Braces size={18} className="text-moss" />
                    <h2 className="font-black">Structured & judged</h2>
                  </div>
                  <div className="mt-4 space-y-3">
                    <details
                      className="rounded-xl border border-line bg-white"
                      open={Boolean(structured)}
                    >
                      <summary className="cursor-pointer px-3 py-2.5 text-xs font-black uppercase tracking-[0.1em]">
                        Structured output
                      </summary>
                      <pre className="max-h-96 overflow-auto border-t border-line p-3 text-[11px] leading-5">
                        {structured ? pretty(structured) : "null"}
                      </pre>
                    </details>
                    <details
                      className="rounded-xl border border-line bg-white"
                      open={Boolean(judged)}
                    >
                      <summary className="cursor-pointer px-3 py-2.5 text-xs font-black uppercase tracking-[0.1em]">
                        Judge scores
                      </summary>
                      <pre className="max-h-96 overflow-auto border-t border-line p-3 text-[11px] leading-5">
                        {judged ? pretty(judged) : "Chưa có judged record."}
                      </pre>
                    </details>
                    <details className="rounded-xl border border-line bg-white">
                      <summary className="cursor-pointer px-3 py-2.5 text-xs font-black uppercase tracking-[0.1em]">
                        Gold sample
                      </summary>
                      <pre className="max-h-96 overflow-auto border-t border-line p-3 text-[11px] leading-5">
                        {pretty(sample)}
                      </pre>
                    </details>
                  </div>
                </Card>
              </div>
            </>
          ) : (
            <Card className="p-6">
              <EmptyState
                title="Chọn một sample"
                description="Panel chi tiết sẽ hiển thị answer, trace, structured JSON, judge scores và diff cùng sample_id."
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function AnswerPanel({
  label,
  answer,
  ok,
}: {
  label: string;
  answer: string;
  ok: boolean;
}) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="font-black">{label}</p>
        <Pill tone={ok ? "good" : "bad"}>{ok ? "OK" : "FAIL / missing"}</Pill>
      </div>
      <div className="mt-3 max-h-[430px] overflow-auto whitespace-pre-wrap text-sm leading-7 text-ink/70">
        {answer}
      </div>
    </div>
  );
}

function TraceField({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null) return null;
  return (
    <div className="rounded-xl bg-canvas/60 px-3 py-3">
      <p className="text-[10px] font-black uppercase tracking-[0.1em] text-ink/40">
        {label}
      </p>
      <pre className="mt-1 overflow-auto whitespace-pre-wrap text-xs leading-5">
        {typeof value === "string" ? value : pretty(value)}
      </pre>
    </div>
  );
}
