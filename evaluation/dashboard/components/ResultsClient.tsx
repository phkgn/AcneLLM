"use client";

import {
  Database,
  RefreshCw,
  ShieldCheck,
  Sigma,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
  formatMetric,
  inputClass,
} from "./ui";

type JsonRecord = Record<string, unknown>;

type MetaResponse = {
  reportRuns: string[];
  judgeCalibration: {
    available: boolean;
    calibrated: boolean;
    failedChecks: string[];
  };
};

type ResultsResponse = {
  experiment: string;
  report: JsonRecord | null;
  runMeta: JsonRecord | null;
  units: Record<string, JsonRecord | null>;
  retrieval: { name: string; summary: JsonRecord } | null;
  validation: {
    name: string;
    path: string;
    modifiedAt: string;
    summary: {
      verdict?: "TRUSTWORTHY" | "PARTIAL" | "NOT_TRUSTWORTHY";
      conflicts_n?: number;
      per_check?: Array<{
        name?: string;
        status?: "PASS" | "FAIL" | "WARN" | "SKIPPED";
      }>;
      confidence_notes?: string[];
      tier_verdicts?: Record<string, { verdict?: string; reason?: string }>;
    };
  } | null;
  gates: {
    checks: Array<{
      section: string;
      metric: string;
      threshold: number;
      value: number | null;
      status: "pass" | "fail" | "missing";
      comparison: string;
      system?: string;
    }>;
    summary: { pass: number; fail: number; missing: number };
  };
};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function valueAt(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => record(current)[key], value);
}

function metricValue(system: JsonRecord, path: string) {
  return valueAt(system, path);
}

function pValue(comp: JsonRecord, axis: string) {
  return valueAt(comp, `${axis}.wilcoxon.p_value`);
}

const metricRows = [
  { label: "OK rate", path: "ok_rate", percent: true },
  { label: "Parse success", path: "parse_success_rate", percent: true },
  { label: "Citation valid", path: "citation_valid_rate", percent: true },
  { label: "Pregnancy safety", path: "pregnancy_safety_rate", percent: true },
  { label: "Faithfulness", path: "faithfulness_mean", percent: true },
  { label: "Judge correctness", path: "judge_means.correctness", percent: false },
  { label: "Judge safety", path: "judge_means.safety", percent: false },
  { label: "P50 latency", path: "latency_ms.p50", percent: false, suffix: " ms" },
];

export function ResultsClient() {
  const [runs, setRuns] = useState<string[]>([]);
  const [experiment, setExperiment] = useState("main_2x2_t3");
  const [data, setData] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [paretoSystem, setParetoSystem] = useState("s3");
  const [judgeCalibration, setJudgeCalibration] =
    useState<MetaResponse["judgeCalibration"] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `/api/results?experiment=${encodeURIComponent(experiment)}`,
        { cache: "no-store" },
      );
      const body = (await response.json()) as ResultsResponse & { error?: string };
      if (!response.ok) throw new Error(body.error ?? "Không thể đọc results.");
      setData(body);
    } catch (loadError) {
      setError((loadError as Error).message);
    } finally {
      setLoading(false);
    }
  }, [experiment]);

  useEffect(() => {
    void fetch("/api/meta", { cache: "no-store" })
      .then((response) => response.json())
      .then((body: MetaResponse) => {
        const options = Array.from(
          new Set(["main_2x2_t3", ...(body.reportRuns ?? [])]),
        );
        setRuns(options);
        setJudgeCalibration(body.judgeCalibration);
      });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reportSystems = record(data?.report?.systems);
  const systemIds = ["s0", "s1", "s2", "s3", "s4"].filter(
    (system) => Object.keys(record(reportSystems[system])).length,
  );
  const comparisons = record(data?.report?.comparisons);
  const holm = record(data?.report?.holm_correction);
  const pareto = useMemo(() => {
    const rows = record(reportSystems[paretoSystem]).error_pareto;
    if (!Array.isArray(rows)) return [];
    return rows
      .filter((item): item is [string, number] =>
        Array.isArray(item) &&
        typeof item[0] === "string" &&
        typeof item[1] === "number",
      )
      .map(([code, count]) => ({
        code: code.replace(/^E\d+_/, ""),
        count,
      }));
  }, [paretoSystem, reportSystems]);

  const retrievalModes = record(data?.retrieval?.summary.modes);

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title="Kết quả và so sánh S0–S4"
        description="Đọc report thật từ harness, hiển thị paired statistics, Pareto lỗi, T1 unit reports và T2 retrieval summary mới nhất."
        actions={
          <div className="flex gap-2">
            <select
              value={experiment}
              onChange={(event) => setExperiment(event.target.value)}
              className={`${inputClass} min-w-48`}
            >
              {runs.map((run) => (
                <option key={run} value={run}>
                  {run}
                </option>
              ))}
            </select>
            <Button variant="ghost" onClick={() => void load()}>
              <RefreshCw size={16} />
              Refresh
            </Button>
          </div>
        }
      />

      {error ? (
        <div className="mb-5 rounded-2xl border border-ember/20 bg-ember/10 px-4 py-3 text-sm font-bold text-ember">
          {error}
        </div>
      ) : null}

      {judgeCalibration && !judgeCalibration.calibrated ? (
        <div className="mb-5 flex gap-3 rounded-2xl border border-clay/30 bg-clay/10 px-4 py-3 text-sm text-ink/78">
          <TriangleAlert className="mt-0.5 shrink-0 text-clay" size={18} />
          <div>
            <p className="font-black">Điểm judge chưa calibrated</p>
            <p className="mt-1 text-xs leading-5 text-ink/52">
              {judgeCalibration.available
                ? `Các check chưa pass: ${judgeCalibration.failedChecks.join(", ")}.`
                : "Chưa có evaluation/reports/judge_bias_tests.json."}{" "}
              Judge metrics chỉ nên dùng để tham khảo.
            </p>
          </div>
        </div>
      ) : null}

      {data?.validation ? (
        <Card className="mb-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Validation loop
              </p>
              <h2 className="mt-1 text-xl font-black">
                {data.validation.summary.verdict ?? "UNKNOWN"}
              </h2>
              <p className="mt-1 font-mono text-[11px] text-ink/42">
                {data.validation.path}
              </p>
            </div>
            <Pill
              tone={
                data.validation.summary.verdict === "TRUSTWORTHY"
                  ? "good"
                  : data.validation.summary.verdict === "NOT_TRUSTWORTHY"
                    ? "bad"
                    : "warn"
              }
            >
              {data.validation.summary.conflicts_n ?? 0} conflicts
            </Pill>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {(data.validation.summary.per_check ?? []).map((check) => (
              <div
                key={check.name}
                className="flex items-center justify-between gap-3 rounded-xl border border-line bg-canvas/45 px-3 py-2.5"
              >
                <span className="min-w-0 truncate text-xs font-black">
                  {check.name}
                </span>
                <Pill
                  tone={
                    check.status === "PASS"
                      ? "good"
                      : check.status === "FAIL"
                        ? "bad"
                        : "warn"
                  }
                >
                  {check.status}
                </Pill>
              </div>
            ))}
          </div>
          {(data.validation.summary.confidence_notes ?? []).length ? (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-xs leading-5 text-ink/50">
              {data.validation.summary.confidence_notes?.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-5 sm:px-6">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
              Main table
            </p>
            <h2 className="mt-1 text-xl font-black">Per-system metrics</h2>
          </div>
          {data?.report?.generated_at ? (
            <Pill tone="neutral">
              {new Date(String(data.report.generated_at)).toLocaleString("vi-VN")}
            </Pill>
          ) : null}
        </div>
        {systemIds.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[850px] border-collapse text-sm">
              <thead>
                <tr className="bg-canvas/55 text-left">
                  <th className="border-b border-line px-5 py-3 text-xs font-black uppercase tracking-[0.12em] text-ink/45">
                    Metric
                  </th>
                  {systemIds.map((system) => (
                    <th
                      key={system}
                      className="border-b border-line px-5 py-3 text-center text-xs font-black uppercase tracking-[0.12em]"
                    >
                      {system}
                      <span className="mt-1 block text-[10px] normal-case tracking-normal text-ink/38">
                        n={String(record(reportSystems[system]).n ?? "—")}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricRows.map((metric, index) => (
                  <tr key={metric.path} className={index % 2 ? "bg-canvas/30" : ""}>
                    <td className="border-b border-line px-5 py-3.5 font-black">
                      {metric.label}
                    </td>
                    {systemIds.map((system) => {
                      const value = metricValue(record(reportSystems[system]), metric.path);
                      return (
                        <td
                          key={system}
                          className="border-b border-line px-5 py-3.5 text-center font-bold tabular-nums"
                        >
                          {formatMetric(value, metric.percent)}
                          {typeof value === "number" ? metric.suffix ?? "" : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6">
            <EmptyState
              title={loading ? "Đang đọc report…" : "Chưa có report.json"}
              description="Chạy T3 generation, judge (nếu cần) và command report. Dashboard không tạo metric giả khi artifact chưa tồn tại."
            />
          </div>
        )}
      </Card>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
        <Card className="p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Paired statistics
              </p>
              <h2 className="mt-1 text-xl font-black">Pre-registered comparisons</h2>
            </div>
            <Sigma size={22} className="text-moss" />
          </div>
          <div className="mt-5 space-y-3">
            {Object.entries(comparisons).map(([pair, rawComp]) => {
              const comp = record(rawComp);
              return (
                <div
                  key={pair}
                  className="rounded-2xl border border-line bg-canvas/45 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-black">{pair.replace(":", " vs ")}</p>
                    <Pill tone="neutral">
                      n={String(comp.n_common ?? "—")}
                    </Pill>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {["correctness", "safety"].map((axis) => {
                      const correction = record(holm[`${pair}:${axis}`]);
                      const significant = correction.significant === true;
                      const wtl = record(valueAt(comp, `${axis}.wtl_b_vs_a`));
                      return (
                        <div key={axis} className="rounded-xl bg-[#211f1b] px-3 py-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-black uppercase tracking-[0.1em]">
                              {axis}
                            </span>
                            <Pill tone={significant ? "good" : "neutral"}>
                              {significant ? "Holm sig." : "not sig."}
                            </Pill>
                          </div>
                          <p className="mt-2 text-xs text-ink/50">
                            p={String(pValue(comp, axis) ?? "—")} · W/T/L{" "}
                            {String(wtl.win ?? "—")}/{String(wtl.tie ?? "—")}/
                            {String(wtl.loss ?? "—")}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            {!Object.keys(comparisons).length ? (
              <EmptyState
                title="Chưa có paired comparisons"
                description="Các comparison xuất hiện sau khi có judged files và chạy analysis.report."
              />
            ) : null}
          </div>
        </Card>

        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Error attribution
              </p>
              <h2 className="mt-1 text-xl font-black">Pareto lỗi</h2>
            </div>
            <div className="flex gap-1">
              {systemIds.map((system) => (
                <button
                  key={system}
                  onClick={() => setParetoSystem(system)}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-black uppercase ${
                    paretoSystem === system
                      ? "bg-clay text-white"
                      : "border border-line bg-[#211f1b] text-ink/45"
                  }`}
                >
                  {system}
                </button>
              ))}
            </div>
          </div>
          {pareto.length ? (
            <div className="mt-5 h-[330px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pareto} layout="vertical" margin={{ left: 14 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#37342e" />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="code"
                    width={140}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(217,119,87,0.10)" }}
                    contentStyle={{
                      borderRadius: 12,
                      borderColor: "#37342e",
                      background: "#1c1b18",
                      color: "#eeeae3",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="count" fill="#d97757" radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-5">
              <EmptyState
                title="Chưa có Pareto data"
                description="Error counts được report generator tổng hợp từ trace và deterministic attribution."
              />
            </div>
          )}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Tier 1
              </p>
              <h2 className="mt-1 text-xl font-black">Unit reports</h2>
            </div>
            <ShieldCheck size={22} className="text-moss" />
          </div>
          <div className="mt-5 space-y-3">
            <UnitSummary name="Intent router" report={data?.units.intent_router} />
            <UnitSummary name="Query planner" report={data?.units.query_planner} />
            <UnitSummary name="Guardrails" report={data?.units.guardrails} />
            <UnitSummary name="Normalizer" report={data?.units.normalizer} />
          </div>
        </Card>

        <Card className="p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Tier 2
              </p>
              <h2 className="mt-1 text-xl font-black">Retrieval modes</h2>
            </div>
            <Database size={22} className="text-moss" />
          </div>
          {Object.keys(retrievalModes).length ? (
            <>
              <p className="mt-2 text-xs text-ink/45">
                Latest run: {data?.retrieval?.name}
              </p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[650px] text-sm">
                  <thead>
                    <tr className="text-left text-[10px] font-black uppercase tracking-[0.1em] text-ink/42">
                      <th className="border-b border-line py-2 pr-3">Mode</th>
                      {["hit@3", "hit@5", "mrr@10", "ndcg@5", "irrelevant@5", "latency_ms_mean"].map(
                        (metric) => (
                          <th key={metric} className="border-b border-line px-2 py-2 text-right">
                            {metric}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(retrievalModes).map(([mode, rawMetrics]) => {
                      const metrics = record(rawMetrics);
                      return (
                        <tr key={mode}>
                          <td className="border-b border-line py-3 pr-3 font-black">
                            {mode}
                          </td>
                          {["hit@3", "hit@5", "mrr@10", "ndcg@5", "irrelevant@5", "latency_ms_mean"].map(
                            (metric) => (
                              <td
                                key={metric}
                                className="border-b border-line px-2 py-3 text-right font-bold tabular-nums"
                              >
                                {formatMetric(
                                  metrics[metric],
                                  metric !== "latency_ms_mean",
                                )}
                              </td>
                            ),
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="mt-5">
              <EmptyState
                title="Chưa có retrieval summary"
                description="Chạy T2 retrieval để tạo reports/retrieval/<timestamp>/summary.json."
              />
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-5 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
              Regression gate
            </p>
            <h2 className="mt-1 text-xl font-black">Metric vs threshold</h2>
          </div>
          {data ? (
            <div className="flex gap-2">
              <Pill tone="good">{data.gates.summary.pass} pass</Pill>
              <Pill tone={data.gates.summary.fail ? "bad" : "neutral"}>
                {data.gates.summary.fail} fail
              </Pill>
              <Pill tone="neutral">{data.gates.summary.missing} missing</Pill>
            </div>
          ) : null}
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {data?.gates.checks.map((gate) => (
            <div
              key={`${gate.section}-${gate.metric}`}
              className="rounded-2xl border border-line bg-canvas/45 p-4"
            >
              <div className="flex justify-between gap-2">
                <span className="text-[10px] font-black uppercase tracking-[0.12em] text-ink/40">
                  {gate.section}
                </span>
                <Pill
                  tone={
                    gate.status === "pass"
                      ? "good"
                      : gate.status === "fail"
                        ? "bad"
                        : "neutral"
                  }
                >
                  {gate.status}
                </Pill>
              </div>
              <p className="mt-3 break-words text-sm font-black">{gate.metric}</p>
              <p className="mt-1 text-xs text-ink/45">
                {gate.value ?? "—"} {gate.comparison} {gate.threshold}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

function UnitSummary({
  name,
  report,
}: {
  name: string;
  report: JsonRecord | null | undefined;
}) {
  const headline = report
    ? Object.entries(report)
        .filter(([, value]) => typeof value === "number")
        .slice(0, 4)
    : [];
  return (
    <div className="rounded-2xl border border-line bg-canvas/45 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-black">{name}</p>
        <Pill tone={report ? "good" : "neutral"}>{report ? "available" : "missing"}</Pill>
      </div>
      {headline.length ? (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {headline.map(([metric, value]) => (
            <div key={metric} className="rounded-xl bg-[#211f1b] px-3 py-2">
              <p className="truncate text-[10px] font-black uppercase tracking-[0.08em] text-ink/40">
                {metric}
              </p>
              <p className="mt-1 text-sm font-black">{formatMetric(value)}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-xs leading-5 text-ink/45">
          {report
            ? "Report có cấu trúc lồng nhau; mở Inspect hoặc file API để xem chi tiết."
            : "Chưa có artifact."}
        </p>
      )}
    </div>
  );
}
