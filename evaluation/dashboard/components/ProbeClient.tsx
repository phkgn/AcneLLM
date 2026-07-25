"use client";

import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Loader2,
  Play,
  Radar,
  XCircle,
} from "lucide-react";
import { useCallback, useState } from "react";
import {
  Button,
  Card,
  PageHeader,
  Pill,
  formatDuration,
  inputClass,
} from "./ui";

type Intent = "advise" | "knowledge" | "clarify" | "reject";
type Tone = "good" | "bad" | "warn" | "neutral" | "info";

interface Neighbor {
  rank: number;
  label: string;
  similarity: number;
  text: string;
}

interface ProbeResult {
  primary_intent: Intent;
  nearest_similarity: number;
  nearest_distance: number;
  vote_scores: Record<string, number>;
  vote_margin: number;
  neighbor_labels: string[];
  neighbor_similarities: number[];
  ambiguity_reason: string | null;
  effective_k: number;
  effective_oos_threshold: number;
  effective_margin: number;
  model_name: string;
  indexed_rows: number;
  cache_hit?: boolean;
  correct: boolean | null;
  neighbors?: Neighbor[];
}

interface ProbeResponse {
  result?: ProbeResult;
  command?: string;
  durationMs?: number;
  error?: string;
}

interface BatchRow {
  text: string;
  expected: Intent | null;
  result: ProbeResult | null;
  error: string | null;
}

const IN_SCOPE: Array<"advise" | "knowledge" | "clarify"> = [
  "advise",
  "knowledge",
  "clarify",
];

const ALL_INTENTS: readonly Intent[] = [...IN_SCOPE, "reject"];

function parseExpect(raw: string | undefined): Intent | null {
  const trimmed = raw?.trim() ?? "";
  return (ALL_INTENTS as readonly string[]).includes(trimmed)
    ? (trimmed as Intent)
    : null;
}

const DEFAULTS = { k: 9, oos: 0.483609, margin: 0.08 };

function intentTone(intent: string): Tone {
  if (intent === "reject") return "bad";
  if (intent === "clarify") return "warn";
  if (intent === "advise" || intent === "knowledge") return "good";
  return "neutral";
}

function fmt(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function parseOptionalNumber(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function ProbeClient() {
  const [text, setText] = useState("");
  const [kInput, setKInput] = useState("");
  const [oosInput, setOosInput] = useState("");
  const [marginInput, setMarginInput] = useState("");
  const [expect, setExpect] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [meta, setMeta] = useState<{ command: string; durationMs: number } | null>(
    null,
  );

  const [batchInput, setBatchInput] = useState("");
  const [batchRows, setBatchRows] = useState<BatchRow[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState("");

  const runProbe = useCallback(
    async (payload: Record<string, unknown>): Promise<ProbeResponse> => {
      const response = await fetch("/api/probe/semantic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      const body = (await response.json()) as ProbeResponse;
      if (!response.ok || !body.result) {
        throw new Error(body.error ?? `HTTP ${response.status}`);
      }
      return body;
    },
    [],
  );

  const buildPayload = useCallback(
    (sentence: string, expected: string): Record<string, unknown> => {
      const payload: Record<string, unknown> = { text: sentence };
      const k = parseOptionalNumber(kInput);
      const oos = parseOptionalNumber(oosInput);
      const margin = parseOptionalNumber(marginInput);
      if (k !== undefined) payload.k = k;
      if (oos !== undefined) payload.oos = oos;
      if (margin !== undefined) payload.margin = margin;
      if (expected) payload.expect = expected;
      return payload;
    },
    [kInput, oosInput, marginInput],
  );

  const runSingle = useCallback(async () => {
    const sentence = text.trim();
    if (!sentence || loading) return;
    setLoading(true);
    setError("");
    try {
      const body = await runProbe(buildPayload(sentence, expect));
      setResult(body.result ?? null);
      setMeta({
        command: body.command ?? "",
        durationMs: body.durationMs ?? 0,
      });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }, [text, loading, expect, runProbe, buildPayload]);

  const runBatch = useCallback(async () => {
    if (batchRunning) return;
    const rows: BatchRow[] = batchInput
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [sentence, expectedRaw] = line.split("\t");
        return {
          text: sentence.trim(),
          expected: parseExpect(expectedRaw),
          result: null,
          error: null,
        };
      })
      .filter((row) => row.text);
    if (!rows.length) return;
    setBatchRows(rows);
    setBatchRunning(true);
    setError("");
    for (let index = 0; index < rows.length; index += 1) {
      setBatchProgress(`Đang chạy ${index + 1}/${rows.length}…`);
      try {
        const body = await runProbe(
          buildPayload(rows[index].text, rows[index].expected ?? ""),
        );
        rows[index] = { ...rows[index], result: body.result ?? null };
      } catch (cause) {
        rows[index] = { ...rows[index], error: (cause as Error).message };
      }
      setBatchRows([...rows]);
    }
    setBatchProgress("");
    setBatchRunning(false);
  }, [batchInput, batchRunning, runProbe, buildPayload]);

  const judged = batchRows.filter((row) => row.expected && row.result);
  const batchCorrect = judged.filter(
    (row) => row.result?.primary_intent === row.expected,
  ).length;

  return (
    <div>
      <PageHeader
        eyebrow="Diagnostics"
        title="Router Probe"
        description="Gõ một câu tiếng Việt để xem SemanticRouter (embedding kNN) phân loại ra sao và tại sao: cổng OOS, vote scores, biên ambiguity và các câu train khớp nhất."
      />

      <Card className="p-5">
        <label
          htmlFor="probe-text"
          className="mb-2 block text-xs font-semibold uppercase tracking-[0.12em] text-muted"
        >
          Câu đầu vào (tiếng Việt)
        </label>
        <textarea
          id="probe-text"
          className={`${inputClass} min-h-[72px] resize-y`}
          placeholder="vd: da mình mụn viêm nhiều nên dùng gì?"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void runSingle();
            }
          }}
        />

        <details className="mt-4 rounded-xl border border-line bg-sand/30 px-4 py-3">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-ink">
            <ChevronDown size={15} className="text-muted" />
            Thresholds (để trống = mặc định của router)
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <NumberField
              label={`k (mặc định ${DEFAULTS.k})`}
              value={kInput}
              onChange={setKInput}
              min={1}
              max={100}
              step={1}
            />
            <NumberField
              label={`oos_distance_threshold (mặc định ${DEFAULTS.oos})`}
              value={oosInput}
              onChange={setOosInput}
              min={0}
              max={2}
              step={0.001}
            />
            <NumberField
              label={`ambiguity_margin (mặc định ${DEFAULTS.margin})`}
              value={marginInput}
              onChange={setMarginInput}
              min={0}
              max={1}
              step={0.01}
            />
          </div>
        </details>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <select
            aria-label="Kỳ vọng"
            className={`${inputClass} w-auto`}
            value={expect}
            onChange={(event) => setExpect(event.target.value)}
          >
            <option value="">Kỳ vọng: (không chọn)</option>
            {ALL_INTENTS.map((intent) => (
              <option key={intent} value={intent}>
                Kỳ vọng: {intent}
              </option>
            ))}
          </select>
          <Button
            onClick={() => void runSingle()}
            disabled={loading || !text.trim()}
          >
            {loading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Play size={15} />
            )}
            {loading ? "Đang load embedder…" : "Run"}
          </Button>
          <span className="text-xs text-muted">
            Mỗi lần chạy spawn Python và load embedder (~10–30s trên CPU).
          </span>
        </div>
      </Card>

      {error ? (
        <Card className="mt-5 border-[#523029] bg-[#321e1a]/60 p-4">
          <p className="flex items-start gap-2 text-sm text-[#ef8e78]">
            <CircleAlert size={16} className="mt-0.5 shrink-0" />
            <span className="whitespace-pre-wrap">{error}</span>
          </p>
        </Card>
      ) : null}

      {result ? (
        <ResultView result={result} meta={meta} />
      ) : !loading && !error ? (
        <p className="mt-6 text-sm text-muted">
          Chưa có kết quả — nhập một câu rồi bấm Run (hoặc Enter).
        </p>
      ) : null}

      <Card className="mt-8 p-5">
        <details>
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-ink">
            <ChevronDown size={15} className="text-muted" />
            Batch mini — mỗi dòng một câu, thêm <code>\t&lt;expect&gt;</code> nếu muốn chấm điểm
          </summary>
          <textarea
            className={`${inputClass} mt-3 min-h-[120px] resize-y font-mono text-[13px]`}
            placeholder={"mụn đầu đen hình thành thế nào?\tknowledge\ngiá vàng hôm nay bao nhiêu?\treject"}
            value={batchInput}
            onChange={(event) => setBatchInput(event.target.value)}
          />
          <div className="mt-3 flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => void runBatch()}
              disabled={batchRunning || !batchInput.trim()}
            >
              {batchRunning ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Play size={15} />
              )}
              Run batch
            </Button>
            {batchProgress ? (
              <span className="text-xs text-muted">{batchProgress}</span>
            ) : null}
            {judged.length ? (
              <Pill tone={batchCorrect === judged.length ? "good" : "warn"}>
                Accuracy: {batchCorrect}/{judged.length} (
                {((batchCorrect / judged.length) * 100).toFixed(0)}%)
              </Pill>
            ) : null}
          </div>

          {batchRows.length ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[13px]">
                <thead>
                  <tr className="border-b border-line text-xs uppercase tracking-[0.1em] text-muted">
                    <th className="px-2 py-2">Text</th>
                    <th className="px-2 py-2">Predicted</th>
                    <th className="px-2 py-2">Expected</th>
                    <th className="px-2 py-2">Đúng?</th>
                    <th className="px-2 py-2">Nearest sim</th>
                  </tr>
                </thead>
                <tbody>
                  {batchRows.map((row, index) => (
                    <tr key={index} className="border-b border-line/60 align-top">
                      <td className="max-w-[380px] px-2 py-2 text-ink">
                        {row.text}
                        {row.error ? (
                          <span className="mt-1 block text-xs text-[#ef8e78]">
                            {row.error}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-2 py-2">
                        {row.result ? (
                          <Pill tone={intentTone(row.result.primary_intent)}>
                            {row.result.primary_intent}
                          </Pill>
                        ) : row.error ? (
                          <Pill tone="bad">error</Pill>
                        ) : (
                          <Loader2 size={14} className="animate-spin text-muted" />
                        )}
                      </td>
                      <td className="px-2 py-2 text-muted">
                        {row.expected ?? "—"}
                      </td>
                      <td className="px-2 py-2">
                        {row.expected && row.result ? (
                          row.result.primary_intent === row.expected ? (
                            <CheckCircle2 size={16} className="text-[#8fbc98]" />
                          ) : (
                            <XCircle size={16} className="text-[#ef8e78]" />
                          )
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-2 py-2 font-mono text-xs text-muted">
                        {row.result ? fmt(row.result.nearest_similarity) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </details>
      </Card>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-muted">
        {label}
      </span>
      <input
        type="number"
        className={inputClass}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function ResultView({
  result,
  meta,
}: {
  result: ProbeResult;
  meta: { command: string; durationMs: number } | null;
}) {
  const isReject = result.primary_intent === "reject";
  const inDomain = result.nearest_distance <= result.effective_oos_threshold;
  const marginPass = result.vote_margin >= result.effective_margin;
  const votes = IN_SCOPE.map((label) => ({
    label,
    score: result.vote_scores[label] ?? 0,
  }));
  const maxVote = Math.max(...votes.map((vote) => vote.score));
  const distancePct = Math.min(100, Math.max(0, result.nearest_distance * 100));
  const thresholdPct = Math.min(
    100,
    Math.max(0, result.effective_oos_threshold * 100),
  );

  return (
    <div className="mt-6 space-y-5">
      <Card className="flex flex-wrap items-center gap-4 p-5">
        <Radar size={22} className="text-clay" />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Verdict
          </p>
          <p className="mt-1">
            <Pill tone={intentTone(result.primary_intent)}>
              <span className="px-1 text-sm">{result.primary_intent}</span>
            </Pill>
          </p>
        </div>
        {result.correct !== null && result.correct !== undefined ? (
          <Pill tone={result.correct ? "good" : "bad"}>
            {result.correct ? (
              <span className="flex items-center gap-1">
                <CheckCircle2 size={13} /> khớp kỳ vọng
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <XCircle size={13} /> sai kỳ vọng
              </span>
            )}
          </Pill>
        ) : null}
        {result.cache_hit === false ? (
          <Pill tone="info">index vừa được dựng lần đầu</Pill>
        ) : null}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Cổng OOS
          </p>
          <div className="relative mt-4 h-3 rounded-full bg-sand">
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${
                inDomain ? "bg-[#52745a]" : "bg-[#a94d3e]"
              }`}
              style={{ width: `${distancePct}%` }}
            />
            <div
              className="absolute -inset-y-1 w-0.5 bg-clay"
              style={{ left: `${thresholdPct}%` }}
              title={`threshold ${fmt(result.effective_oos_threshold)}`}
            />
          </div>
          <p className="mt-3 text-sm text-ink">
            distance <span className="font-mono">{fmt(result.nearest_distance)}</span>{" "}
            {inDomain ? "≤" : ">"} threshold{" "}
            <span className="font-mono">{fmt(result.effective_oos_threshold)}</span>{" "}
            →{" "}
            <span className="font-semibold">
              {inDomain ? "IN-DOMAIN" : "REJECT (OOS)"}
            </span>
          </p>
          <p className="mt-1 text-xs text-muted">
            nearest_similarity ={" "}
            <span className="font-mono">{fmt(result.nearest_similarity)}</span>
          </p>
        </Card>

        <Card className="p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Cổng ambiguity
          </p>
          <p className="mt-4 text-sm text-ink">
            vote_margin <span className="font-mono">{fmt(result.vote_margin)}</span>{" "}
            {marginPass ? "≥" : "<"} margin{" "}
            <span className="font-mono">{fmt(result.effective_margin)}</span> →{" "}
            <span className="font-semibold">
              {isReject
                ? "bỏ qua (đã reject ở cổng OOS)"
                : marginPass
                  ? "giữ winner"
                  : "CLARIFY"}
            </span>
          </p>
          {result.ambiguity_reason ? (
            <p className="mt-2 break-all rounded-lg bg-sand/50 px-3 py-2 font-mono text-[11px] text-muted">
              {result.ambiguity_reason}
            </p>
          ) : null}
        </Card>
      </div>

      <Card className="p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
          Vote scores (k={result.effective_k})
        </p>
        <div className="mt-4 space-y-3">
          {votes.map((vote) => {
            const winner = vote.score === maxVote && vote.score > 0;
            return (
              <div key={vote.label} className="flex items-center gap-3">
                <span
                  className={`w-24 text-sm ${
                    winner ? "font-semibold text-ink" : "text-muted"
                  }`}
                >
                  {vote.label}
                  {winner ? " ◆" : ""}
                </span>
                <div className="h-2.5 flex-1 rounded-full bg-sand">
                  <div
                    className={`h-full rounded-full ${
                      winner ? "bg-clay" : "bg-[#6b6154]"
                    }`}
                    style={{ width: `${Math.min(100, vote.score * 100)}%` }}
                  />
                </div>
                <span className="w-16 text-right font-mono text-xs text-muted">
                  {fmt(vote.score, 3)}
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      {result.neighbors?.length ? (
        <Card className="p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            Neighbors khớp nhất ({result.neighbors.length})
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-[0.1em] text-muted">
                  <th className="px-2 py-2">#</th>
                  <th className="px-2 py-2">Label</th>
                  <th className="px-2 py-2">Similarity</th>
                  <th className="px-2 py-2">Câu train</th>
                </tr>
              </thead>
              <tbody>
                {result.neighbors.map((neighbor) => (
                  <tr
                    key={neighbor.rank}
                    className="border-b border-line/60 align-top"
                  >
                    <td className="px-2 py-2 font-mono text-xs text-muted">
                      {neighbor.rank}
                    </td>
                    <td className="px-2 py-2">
                      <Pill tone={intentTone(neighbor.label)}>
                        {neighbor.label}
                      </Pill>
                    </td>
                    <td className="px-2 py-2 font-mono text-xs text-muted">
                      {fmt(neighbor.similarity)}
                    </td>
                    <td className="px-2 py-2 text-ink">{neighbor.text || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <p className="text-xs text-muted">
        model <span className="font-mono">{result.model_name}</span> · index{" "}
        {result.indexed_rows} rows · k={result.effective_k} · oos=
        {fmt(result.effective_oos_threshold)} · margin=
        {fmt(result.effective_margin)}
        {meta ? ` · ${formatDuration(meta.durationMs)}` : ""}
        {meta?.command ? (
          <span className="mt-1 block break-all font-mono text-[11px] text-muted/70">
            {meta.command}
          </span>
        ) : null}
      </p>
    </div>
  );
}
