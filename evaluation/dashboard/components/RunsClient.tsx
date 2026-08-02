"use client";

import {
  CheckCircle2,
  ChevronRight,
  Circle,
  CircleStop,
  Clock3,
  Filter,
  LoaderCircle,
  MinusCircle,
  Play,
  RotateCcw,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { lineClass } from "@/lib/log-lines";
import {
  parseRunAllSummaryText,
  runAllSummaryPath,
  type RunAllStep,
  type RunAllStepStatus,
  type RunAllSummary,
} from "@/lib/run-all";
import type {
  CatalogDataset,
  CatalogSystem,
  CommandId,
  JobRecord,
} from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
  formatDuration,
  inputClass,
} from "./ui";

type MetaResponse = {
  datasets: CatalogDataset[];
  systems: CatalogSystem[];
  reportRuns?: string[];
};

type ProgressItem = {
  system: string;
  systemLabel: string;
  completed: number;
  total: number;
  percent: number;
  averageMs: number | null;
  etaMs: number | null;
  ok: number;
  failed: number;
  watchPath: string;
};

type ValidationWatch = {
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
  };
};

const commands: Array<{
  id: CommandId;
  label: string;
  description: string;
}> = [
  {
    id: "full_evaluation",
    label: "Chạy toàn bộ đánh giá",
    description: "Chạy tuần tự từ kiểm tra môi trường đến báo cáo và biểu đồ.",
  },
  {
    id: "tests",
    label: "Chạy test harness",
    description: "Kiểm tra tự động toàn bộ mã evaluation.",
  },
  {
    id: "retrieval_eval",
    label: "Đánh giá tìm kiếm tài liệu (RAG)",
    description: "So sánh các chế độ sparse, dense, hybrid, rerank và MMR.",
  },
  {
    id: "answer_generation",
    label: "Sinh câu trả lời (4 cấu hình)",
    description: "Sinh câu trả lời theo các cấu hình model và RAG đã chọn.",
  },
  {
    id: "intake_eval",
    label: "Đánh giá bộ tiếp nhận (Intake)",
    description: "Held-out single-turn, không cache/fallback và có overlap guard.",
  },
  {
    id: "bottleneck_analysis",
    label: "Phân tích nút thắt",
    description: "So sánh baseline với Intake hoàn hảo, RAG hoàn hảo và generator API.",
  },
  {
    id: "llm_scoring",
    label: "Chấm điểm bằng LLM",
    description: "Chấm pointwise, faithfulness và pairwise; có thể phát sinh chi phí API.",
  },
  {
    id: "build_report",
    label: "Tổng hợp báo cáo",
    description: "Tổng hợp metric, paired comparisons và Pareto lỗi.",
  },
  {
    id: "quality_gate",
    label: "Kiểm tra ngưỡng chất lượng",
    description: "Chạy gate.yaml qua harness và cập nhật gate_check.json.",
  },
  {
    id: "trust_audit",
    label: "Kiểm định độ tin cậy",
    description: "Audit data/runtime/invariants/judge, conflicts và reproducibility.",
  },
  {
    id: "figures_kb",
    label: "Biểu đồ: Kho tri thức",
    description: "Tạo biểu đồ về corpus, embedding và chỉ mục tìm kiếm.",
  },
  {
    id: "figures_eval",
    label: "Biểu đồ: Kết quả",
    description: "Tạo biểu đồ metric và so sánh kết quả đánh giá.",
  },
  {
    id: "figures_usage",
    label: "Biểu đồ: Sử dụng",
    description: "Tạo biểu đồ thống kê sử dụng từ dữ liệu runtime.",
  },
  {
    id: "figures_all",
    label: "Biểu đồ: Tất cả",
    description: "Tạo toàn bộ nhóm biểu đồ trong một lần chạy.",
  },
];

function commandLabel(commandId: string): string {
  return (
    commands.find((command) => command.id === commandId)?.label ??
    "Lệnh lịch sử"
  );
}

const retrievalModes = [
  "sparse",
  "dense",
  "hybrid",
  "hybrid_rerank",
  "hybrid_mmr_rerank",
];
const skipSteps = [
  "intake",
  "rag",
  "generation",
  "scoring",
  "bottleneck",
  "figures",
];
const skipStepLabels: Record<string, string> = {
  intake: "Intake",
  rag: "RAG",
  generation: "Sinh câu trả lời",
  scoring: "Chấm điểm + báo cáo",
  bottleneck: "Nút thắt",
  figures: "Biểu đồ",
};
const pairOptions = ["s0:s1", "s0:s2", "s1:s3", "s2:s3"];

function systemLabel(systems: CatalogSystem[], id: string): string {
  return systems.find((system) => system.id === id)?.name ?? id;
}

function jobTone(status: JobRecord["status"]) {
  if (status === "succeeded") return "good" as const;
  if (status === "running") return "info" as const;
  if (status === "stopping") return "warn" as const;
  if (status === "failed" || status === "killed") return "bad" as const;
  return "neutral" as const;
}

function validationTone(verdict: ValidationWatch["summary"]["verdict"]) {
  if (verdict === "TRUSTWORTHY") return "good" as const;
  if (verdict === "NOT_TRUSTWORTHY") return "bad" as const;
  return "warn" as const;
}

function stripAnsi(line: string) {
  return line.replace(
    // eslint-disable-next-line no-control-regex
    /\u001b\[[0-?]*[ -/]*[@-~]/g,
    "",
  );
}

function formatStarted(value: string) {
  return new Date(value).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function GenerationProgressBars({ progress }: { progress: ProgressItem[] }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
            Tiến trình sinh câu trả lời
          </p>
          <h3 className="mt-1 text-base font-black">Tiến độ theo cấu hình</h3>
        </div>
        <Pill tone="info">SSE watched</Pill>
      </div>
      {progress.length ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {progress.map((item) => (
            <div
              key={item.system}
              className="rounded-2xl border border-line bg-canvas/45 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-black">{item.systemLabel}</p>
                  <p className="mt-1 text-xs text-ink/45">
                    {item.ok} OK · {item.failed} failed · avg{" "}
                    {formatDuration(item.averageMs)}
                  </p>
                </div>
                <span className="text-sm font-black">
                  {item.completed}/{item.total || "?"}
                </span>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-moss transition-all"
                  style={{ width: `${item.percent}%` }}
                />
              </div>
              <div className="mt-2 flex justify-between text-[11px] font-bold text-ink/40">
                <span>{item.percent.toFixed(1)}%</span>
                <span>ETA {formatDuration(item.etaMs)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-2 text-xs font-bold text-ink/45">
          <LoaderCircle className="animate-spin text-moss" size={15} />
          Đang chờ artifact cấu hình đầu tiên…
        </div>
      )}
    </div>
  );
}

function stepTone(status: RunAllStepStatus) {
  if (status === "ok") return "good" as const;
  if (status === "fail") return "bad" as const;
  if (status === "running") return "info" as const;
  return "neutral" as const;
}

function StepIcon({
  status,
  live = true,
}: {
  status: RunAllStepStatus;
  live?: boolean;
}) {
  if (status === "running") {
    // Job đã chết: bước còn "running" là bị ngắt, không quay vòng nữa.
    return live ? (
      <LoaderCircle className="animate-spin text-[#83b8cf]" size={18} />
    ) : (
      <XCircle className="text-ember" size={18} />
    );
  }
  if (status === "ok") return <CheckCircle2 className="text-moss" size={18} />;
  if (status === "fail") return <XCircle className="text-ember" size={18} />;
  if (status === "skipped") {
    return <MinusCircle className="text-ink/35" size={18} />;
  }
  return <Circle className="text-ink/20" size={18} />;
}

function stepDuration(step: RunAllStep, now: number): number | null {
  if (typeof step.duration_s === "number") return step.duration_s * 1000;
  if (step.status !== "running" || !step.started_at) return null;
  return Math.max(0, now - new Date(step.started_at).getTime());
}

type BottleneckChipStatus = RunAllStepStatus;

function bottleneckMarkerStates(log: string): Record<string, BottleneckChipStatus> {
  const states: Record<string, BottleneckChipStatus> = {
    z: "pending",
    x: "pending",
    w: "pending",
    y: "pending",
  };
  const marker =
    /^\[runall\].*\bid=bottleneck_(z|x|w|y)\b.*\bstatus=(start|ok|fail|skipped)\b/i;
  for (const rawLine of log.split(/\r?\n/)) {
    const match = stripAnsi(rawLine).match(marker);
    if (!match) continue;
    const arm = match[1].toLowerCase();
    states[arm] = match[2].toLowerCase() === "start"
      ? "running"
      : (match[2].toLowerCase() as BottleneckChipStatus);
  }
  return states;
}

function RunAllMonitor({
  job,
  log,
  progress,
}: {
  job: JobRecord;
  log: string;
  progress: ProgressItem[];
}) {
  const summaryPath = runAllSummaryPath(job.args?.outDir);
  const [summary, setSummary] = useState<RunAllSummary | null>(null);
  const [, setClock] = useState(0);

  useEffect(() => {
    setSummary(null);
    if (!summaryPath) return;
    let cancelled = false;

    const loadSummary = async () => {
      try {
        const response = await fetch(
          `/api/files?path=${encodeURIComponent(summaryPath)}`,
          { cache: "no-store" },
        );
        if (!response.ok || cancelled) return;
        const body = (await response.json()) as { content?: string };
        const parsed = parseRunAllSummaryText(body.content ?? "");
        // Keep the last valid snapshot if a file event races a replacement.
        if (parsed && !cancelled) setSummary(parsed);
      } catch {
        // The summary can be absent briefly before the subprocess starts.
      }
    };

    void loadSummary();
    const source = new EventSource(
      `/api/files/watch?path=${encodeURIComponent(summaryPath)}`,
    );
    const reload = () => void loadSummary();
    source.addEventListener("ready", reload);
    source.addEventListener("chunk", reload);
    source.addEventListener("reset", reload);
    return () => {
      cancelled = true;
      source.close();
    };
  }, [summaryPath]);

  useEffect(() => {
    if (!["running", "stopping"].includes(job.status)) return;
    if (!summary?.steps.some((step) => step.status === "running")) return;
    const timer = setInterval(() => setClock((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [summary, job.status]);

  const markerStates = useMemo(() => bottleneckMarkerStates(log), [log]);
  // Tiến trình chết giữa chừng không kịp ghi trạng thái cuối vào summary.json,
  // nên job đã kết thúc thì mọi bước "running" phải hiểu là bị ngắt.
  const jobLive = ["running", "stopping"].includes(job.status);
  const interruptedStep = !jobLive
    ? summary?.steps.find((step) => step.status === "running")?.id ?? null
    : null;
  const generationRunning =
    jobLive &&
    summary?.steps.find((step) => step.id === "answer_generation")?.status ===
      "running";
  const bottleneckRunning =
    jobLive &&
    summary?.steps.find((step) => step.id === "bottleneck")?.status === "running";
  const now = Date.now();

  return (
    <div className="border-b border-line bg-canvas/25 px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
            Theo dõi đánh giá đầy đủ
          </p>
          <h3 className="mt-1 text-lg font-black">Tiến trình 7 bước</h3>
          {summaryPath ? (
            <p className="mt-1 font-mono text-[11px] text-ink/35">{summaryPath}</p>
          ) : null}
        </div>
        <Pill tone={summary ? "info" : "neutral"}>
          {summary ? "Live summary" : "Đang chờ summary"}
        </Pill>
      </div>

      {!jobLive && interruptedStep ? (
        <div className="mt-4 rounded-xl border border-ember/20 bg-ember/10 px-3 py-2.5 text-sm font-bold text-ember">
          Run đã dừng ({job.status}) khi đang ở bước{" "}
          {summary?.steps.find((step) => step.id === interruptedStep)?.label ??
            interruptedStep}
          . Các bước sau không chạy — chạy lại để tiếp tục.
        </div>
      ) : null}

      {summary ? (
        <div className="mt-4 space-y-2">
          {summary.steps.map((step, index) => {
            const duration = stepDuration(step, now);
            return (
              <div
                key={step.id}
                className="flex items-start gap-3 rounded-xl border border-line bg-[#211f1b]/70 px-3 py-3"
              >
                <span className="mt-0.5 shrink-0">
                  <StepIcon status={step.status} live={jobLive} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-black text-ink/30">
                      {index + 1}/7
                    </span>
                    <span className="text-sm font-black">{step.label}</span>
                    <Pill tone={stepTone(step.status)}>{step.status}</Pill>
                    {duration !== null ? (
                      <span className="text-xs font-bold text-ink/40">
                        {formatDuration(duration)}
                      </span>
                    ) : null}
                  </div>
                  {step.detail ? (
                    <p className={`mt-1 text-xs leading-5 ${
                      step.status === "fail" ? "text-ember" : "text-ink/45"
                    }`}>
                      {step.detail}
                    </p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-dashed border-line px-3 py-4 text-xs font-bold text-ink/45">
          <LoaderCircle className="animate-spin text-moss" size={16} />
          Chờ orchestrator tạo summary.json…
        </div>
      )}

      {generationRunning ? (
        <div className="mt-4 rounded-2xl border border-line bg-[#181d1a] p-4">
          <GenerationProgressBars progress={progress} />
        </div>
      ) : null}

      {bottleneckRunning ? (
        <div className="mt-4 rounded-2xl border border-line bg-[#181d1a] p-4">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
            Các nhánh phân tích nút thắt
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(["z", "x", "w", "y"] as const).map((arm) => (
              <Pill key={arm} tone={stepTone(markerStates[arm])}>
                {markerStates[arm] === "running" ? (
                  <LoaderCircle className="mr-1 animate-spin" size={11} />
                ) : null}
                {{
                  z: "Thực tế (baseline)",
                  x: "Intake hoàn hảo",
                  w: "RAG hoàn hảo",
                  y: "Generator mạnh (API)",
                }[arm]}{" "}
                · {markerStates[arm]}
              </Pill>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function RunsClient() {
  const [meta, setMeta] = useState<MetaResponse>({ datasets: [], systems: [] });
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [commandId, setCommandId] = useState<CommandId>("full_evaluation");
  const [limit, setLimit] = useState("5");
  const [dataset, setDataset] = useState(
    // Mặc định là bộ test chính; dev_tuning chỉ dùng khi cố ý chọn để chạy thử.
    "evaluation/datasets/v1/answer_quality_test.jsonl",
  );
  const [runDir, setRunDir] = useState("evaluation/reports/main_2x2_t3");
  const [outputDir, setOutputDir] = useState(
    "evaluation/reports/main_2x2_t3",
  );
  const [resumeGeneration, setResumeGeneration] = useState(true);
  const [reproSubset, setReproSubset] = useState("0");
  const [strictValidation, setStrictValidation] = useState(false);
  const [systems, setSystems] = useState<string[]>(["s0", "s1", "s2", "s3", "s4"]);
  const [modes, setModes] = useState<string[]>(retrievalModes);
  const [pairs, setPairs] = useState<string[]>(pairOptions);
  const [skip, setSkip] = useState<string[]>([]);
  const [smoke, setSmoke] = useState(false);
  const [yes, setYes] = useState(false);
  const [rawQuery, setRawQuery] = useState(false);
  const [bottleneckArm, setBottleneckArm] = useState("z");
  const [submitting, setSubmitting] = useState(false);
  const [killingJobId, setKillingJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [log, setLog] = useState("");
  const [filter, setFilter] = useState("");
  const [markerOnly, setMarkerOnly] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [validationWatch, setValidationWatch] =
    useState<ValidationWatch | null>(null);
  const consoleRef = useRef<HTMLDivElement>(null);
  const [, tick] = useState(0);

  const refreshJobs = useCallback(async () => {
    const response = await fetch("/api/jobs", { cache: "no-store" });
    if (!response.ok) return;
    const body = (await response.json()) as { jobs: JobRecord[] };
    setJobs(body.jobs);
    setSelectedJobId((current) => current ?? body.jobs[0]?.jobId ?? null);
  }, []);

  useEffect(() => {
    void Promise.all([
      fetch("/api/meta", { cache: "no-store" })
        .then((response) => response.json())
        .then((body: MetaResponse) => {
          setMeta(body);
          if (
            body.datasets.length &&
            !body.datasets.some((item) => item.path === dataset)
          ) {
            setDataset(body.datasets[0].path);
          }
        }),
      refreshJobs(),
    ]);
    const fromUrl = new URLSearchParams(window.location.search).get("job");
    if (fromUrl) setSelectedJobId(fromUrl);
    const poll = setInterval(() => void refreshJobs(), 1000);
    const clock = setInterval(() => tick((value) => value + 1), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(clock);
    };
    // Dataset is intentionally initialized only once from the catalog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshJobs]);

  const selectedJob = jobs.find((job) => job.jobId === selectedJobId) ?? null;
  const validationJobId =
    selectedJob?.commandId === "trust_audit" ? selectedJob.jobId : null;
  const validationJobStartedAt =
    selectedJob?.commandId === "trust_audit" ? selectedJob.startedAt : null;

  useEffect(() => {
    setLog("");
    if (!selectedJobId) return;
    const source = new EventSource(`/api/jobs/${selectedJobId}/logs/stream`);
    source.addEventListener("chunk", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { chunk: string };
      setLog((current) => (current + payload.chunk).slice(-700_000));
    });
    source.addEventListener("reset", () => setLog(""));
    return () => source.close();
  }, [selectedJobId]);

  useEffect(() => {
    if (autoScroll && consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [autoScroll, log]);

  useEffect(() => {
    setProgress([]);
    if (
      !selectedJob ||
      !["answer_generation", "full_evaluation"].includes(
        selectedJob.commandId,
      )
    ) {
      return;
    }
    let cancelled = false;
    let sources: EventSource[] = [];
    const jobArgs = selectedJob.args ?? {};
    const progressDataset =
      typeof jobArgs.dataset === "string"
        ? jobArgs.dataset
        : "evaluation/datasets/v1/answer_quality_test.jsonl";
    const progressSystems = Array.isArray(jobArgs.systems)
      ? jobArgs.systems.map(String)
      : ["s0", "s1", "s2", "s3", "s4"];
    const progressLimit =
      typeof jobArgs.limit === "number"
        ? jobArgs.limit
        : jobArgs.smoke === true
          ? 10
          : null;
    const progressExperiment =
      typeof jobArgs.outDir === "string"
        ? jobArgs.outDir
            .replace(/\\/g, "/")
            .split("/")
            .filter(Boolean)
            .at(-1) ?? "main_2x2_t3"
        : "main_2x2_t3";
    const query = new URLSearchParams({
      experiment: progressExperiment,
      dataset: progressDataset,
      systems: progressSystems.join(","),
    });
    if (progressLimit) query.set("limit", String(progressLimit));

    const loadProgress = async () => {
      const response = await fetch(`/api/progress?${query}`, {
        cache: "no-store",
      });
      if (!response.ok || cancelled) return null;
      const body = (await response.json()) as { progress: ProgressItem[] };
      if (!cancelled) setProgress(body.progress);
      return body.progress;
    };

    void loadProgress().then((items) => {
      if (!items || cancelled) return;
      sources = items.map((item) => {
        const source = new EventSource(
          `/api/files/watch?path=${encodeURIComponent(item.watchPath)}`,
        );
        source.addEventListener("chunk", () => void loadProgress());
        source.addEventListener("reset", () => void loadProgress());
        return source;
      });
    });
    const poll = setInterval(() => void loadProgress(), 5000);
    return () => {
      cancelled = true;
      clearInterval(poll);
      sources.forEach((source) => source.close());
    };
  }, [selectedJob]);

  useEffect(() => {
    setValidationWatch(null);
    if (!validationJobId || !validationJobStartedAt) return;
    let cancelled = false;
    let source: EventSource | null = null;
    let watchedPath = "";
    const query = new URLSearchParams({ after: validationJobStartedAt });

    const loadValidation = async () => {
      const response = await fetch(`/api/validation?${query}`, {
        cache: "no-store",
      });
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as {
        validation: ValidationWatch | null;
      };
      if (cancelled || !body.validation) return;
      setValidationWatch(body.validation);
      if (body.validation.path !== watchedPath) {
        source?.close();
        watchedPath = body.validation.path;
        source = new EventSource(
          `/api/files/watch?path=${encodeURIComponent(body.validation.path)}`,
        );
        source.addEventListener("chunk", () => void loadValidation());
        source.addEventListener("reset", () => void loadValidation());
      }
    };

    void loadValidation();
    const poll = setInterval(() => void loadValidation(), 2000);
    return () => {
      cancelled = true;
      clearInterval(poll);
      source?.close();
    };
  }, [validationJobId, validationJobStartedAt]);

  const visibleLines = useMemo(() => {
    const allLines = log.split(/\r?\n/).map(stripAnsi);
    const lines = markerOnly
      ? allLines.filter((line) => /^\[runall\]/.test(line))
      : allLines;
    if (!filter) return { lines, error: "" };
    try {
      const regex = new RegExp(filter, "i");
      return { lines: lines.filter((line) => regex.test(line)), error: "" };
    } catch (regexError) {
      return { lines, error: (regexError as Error).message };
    }
  }, [filter, log, markerOnly]);

  function toggle(
    value: string,
    selected: string[],
    setter: (next: string[]) => void,
  ) {
    setter(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value],
    );
  }

  function buildArgs(): Record<string, unknown> {
    const args: Record<string, unknown> = {};
    const parsedLimit = Number(limit);
    if (
      limit &&
      Number.isInteger(parsedLimit) &&
      ![
        "tests",
        "build_report",
        "quality_gate",
        "trust_audit",
      ].includes(commandId)
    ) {
      args.limit = parsedLimit;
    }
    if (commandId === "full_evaluation") {
      if (limit && Number.isInteger(parsedLimit)) args.limit = parsedLimit;
      args.smoke = smoke;
      args.skip = skip;
      // Không override dataset: mỗi bước tự lấy bộ của nó từ config.
      args.yes = yes;
    }
    if (commandId === "retrieval_eval") {
      args.modes = modes;
      args.rawQuery = rawQuery;
    }
    if (commandId === "answer_generation") {
      args.systems = systems;
      args.outDir = outputDir;
      args.resume = resumeGeneration;
    }
    if (commandId === "llm_scoring") {
      args.dataset = dataset;
      args.pairs = pairs;
      args.runDir = runDir;
    }
    if (commandId === "build_report") {
      args.dataset = dataset;
      args.runDir = runDir;
    }
    if (commandId === "quality_gate") args.runDir = runDir;
    if (commandId === "bottleneck_analysis") args.arm = bottleneckArm;
    if (commandId === "trust_audit") {
      args.dataset = dataset;
      args.runDir = runDir;
      args.reproSubset = Number(reproSubset) || 0;
      args.strict = strictValidation;
    }
    return args;
  }

  async function submit() {
    if (
      (commandId === "llm_scoring" ||
        (commandId === "bottleneck_analysis" && bottleneckArm === "y")) &&
      !window.confirm(
        commandId === "bottleneck_analysis"
            ? "Arm Y gọi generator API và judge đã cấu hình, có thể phát sinh chi phí. Tiếp tục?"
            : "Judge đã cấu hình sẽ dùng API key và có thể phát sinh chi phí. Tiếp tục?",
      )
    ) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commandId, args: buildArgs() }),
      });
      const body = (await response.json()) as {
        job?: JobRecord;
        error?: string;
      };
      if (!response.ok || !body.job) throw new Error(body.error ?? "Không thể tạo job.");
      setJobs((current) => [body.job!, ...current]);
      setSelectedJobId(body.job.jobId);
      if (commandId === "answer_generation") setRunDir(outputDir);
      window.history.replaceState(null, "", `/runs?job=${body.job.jobId}`);
    } catch (submitError) {
      setError((submitError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function killSelected() {
    if (
      !selectedJob ||
      !["running", "stopping"].includes(selectedJob.status) ||
      killingJobId
    ) {
      return;
    }
    const jobId = selectedJob.jobId;
    setKillingJobId(jobId);
    setError("");
    setJobs((current) =>
      current.map((job) =>
        job.jobId === jobId
          ? {
              ...job,
              status: "stopping",
              signal: "KILL_REQUESTED",
            }
          : job,
      ),
    );
    try {
      const response = await fetch(`/api/jobs/${jobId}/kill`, {
        method: "POST",
      });
      const body = (await response.json()) as {
        job?: JobRecord;
        error?: string;
      };
      if (!response.ok || !body.job) {
        throw new Error(body.error ?? "Không thể dừng job.");
      }
      setJobs((current) =>
        current.map((job) => (job.jobId === jobId ? body.job! : job)),
      );
    } catch (killError) {
      setError((killError as Error).message);
      await refreshJobs();
    } finally {
      setKillingJobId(null);
    }
  }

  const selectedCommand = commands.find((command) => command.id === commandId)!;
  const elapsedMs = selectedJob
    ? (selectedJob.finishedAt
        ? new Date(selectedJob.finishedAt)
        : new Date()
      ).getTime() - new Date(selectedJob.startedAt).getTime()
    : null;

  return (
    <>
      <PageHeader
        eyebrow="Run builder"
        title="Chạy và theo dõi harness"
        description="Mọi lựa chọn được chuyển thành argv typed và spawn trực tiếp, không qua shell. Log vẫn xem được sau refresh nhờ registry và file tail."
      />

      {error ? (
        <div className="mb-5 rounded-2xl border border-ember/20 bg-ember/10 px-4 py-3 text-sm font-bold text-ember">
          {error}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[390px_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card className="p-5">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Lệnh đánh giá
              </p>
              <h2 className="mt-1 text-xl font-black">Cấu hình chạy</h2>
            </div>
            <label className="mt-5 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
              Runner
              <select
                value={commandId}
                onChange={(event) => setCommandId(event.target.value as CommandId)}
                className={`${inputClass} mt-2`}
              >
                {commands.map((command) => (
                  <option key={command.id} value={command.id}>
                    {command.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="mt-2 text-xs leading-5 text-ink/45">
              {selectedCommand.description}
            </p>
            <datalist id="report-run-directories">
              {Array.from(
                new Set(["main_2x2_t3", ...(meta.reportRuns ?? [])]),
              ).map((name) => (
                <option
                  key={name}
                  value={`evaluation/reports/${name}`}
                />
              ))}
            </datalist>

            {![
              "tests",
              "build_report",
              "quality_gate",
              "trust_audit",
            ].includes(commandId) ? (
              <label className="mt-4 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                Limit
                <input
                  type="number"
                  min={1}
                  max={100000}
                  value={limit}
                  onChange={(event) => setLimit(event.target.value)}
                  className={`${inputClass} mt-2`}
                />
              </label>
            ) : null}

            {commandId === "full_evaluation" ? (
              <div className="mt-4 rounded-xl border border-line bg-canvas/45 p-3">
                <p className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                  Dataset mỗi bước (cố định trong config)
                </p>
                <ul className="mt-2 space-y-1 text-[11px] leading-5 text-ink/55">
                  <li>Đánh giá Intake — <code>intake.val.jsonl</code></li>
                  <li>Đánh giá RAG — <code>retrieval_test.jsonl</code></li>
                  <li>Sinh câu trả lời + Chấm điểm — <code>answer_quality_test.jsonl</code></li>
                  <li>Phân tích nút thắt — <code>retrieval_test.jsonl</code></li>
                </ul>
              </div>
            ) : null}

            {["llm_scoring", "build_report", "trust_audit"].includes(commandId) ? (
              <label className="mt-4 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                Dataset
                <select
                  value={dataset}
                  onChange={(event) => setDataset(event.target.value)}
                  className={`${inputClass} mt-2`}
                >
                  {meta.datasets.map((item) => (
                    <option key={item.path} value={item.path}>
                      {item.name} · {item.rows} rows
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {commandId === "full_evaluation" ? (
              <div className="mt-4 space-y-4">
                <div className="space-y-2">
                  <label className="flex items-start gap-2 text-sm font-bold">
                    <input
                      type="checkbox"
                      checked={smoke}
                      onChange={(event) => setSmoke(event.target.checked)}
                      className="mt-0.5 h-4 w-4 accent-moss"
                    />
                    <span>
                      Chạy thử nhanh
                      <span className="block text-[11px] font-medium text-ink/45">
                        10 mẫu mỗi bước, bỏ qua phân tích nút thắt. Tắt khi chạy chính thức.
                      </span>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 text-sm font-bold">
                    <input
                      type="checkbox"
                      checked={yes}
                      onChange={(event) => setYes(event.target.checked)}
                      className="mt-0.5 h-4 w-4 accent-moss"
                    />
                    <span>
                      Cho phép các bước tốn phí API
                      <span className="block text-[11px] font-medium text-ink/45">
                        Chấm điểm bằng LLM và nút thắt arm Y.
                      </span>
                    </span>
                  </label>
                </div>
                {!yes ? (
                  <p className="rounded-xl bg-[#332719] px-3 py-2.5 text-[11px] leading-5 text-[#e8b96d]">
                    Chưa bật mục tốn phí: chạy nền sẽ <b>bỏ qua chấm điểm và nút thắt</b>{" "}
                    (không hỏi lại được vì job chạy không có bàn phím). Bật nếu muốn kết quả đầy đủ.
                  </p>
                ) : null}
                {smoke ? (
                  <p className="rounded-xl bg-[#332719] px-3 py-2.5 text-[11px] leading-5 text-[#e8b96d]">
                    Đang bật chạy thử nhanh — kết quả chỉ để kiểm tra pipeline, không dùng báo cáo.
                  </p>
                ) : null}
                <fieldset>
                  <legend className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                    Bỏ qua bước (để trống = chạy đủ)
                  </legend>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {skipSteps.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => toggle(item, skip, setSkip)}
                        className={`rounded-lg px-2.5 py-1.5 text-xs font-black ${
                          skip.includes(item)
                            ? "bg-clay text-white"
                            : "border border-line bg-[#211f1b] text-ink/55"
                        }`}
                      >
                        {skipStepLabels[item] ?? item}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </div>
            ) : null}

            {commandId === "retrieval_eval" ? (
              <div className="mt-4 space-y-4">
                <fieldset>
                  <legend className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                    Retrieval modes
                  </legend>
                  <div className="mt-2 grid gap-2">
                    {retrievalModes.map((item) => (
                      <label
                        key={item}
                        className="flex items-center gap-2 text-sm font-bold"
                      >
                        <input
                          type="checkbox"
                          checked={modes.includes(item)}
                          onChange={() => toggle(item, modes, setModes)}
                          className="h-4 w-4 accent-moss"
                        />
                        {item}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <label className="flex items-center gap-2 text-sm font-bold">
                  <input
                    type="checkbox"
                    checked={rawQuery}
                    onChange={(event) => setRawQuery(event.target.checked)}
                    className="h-4 w-4 accent-moss"
                  />
                  Raw query ablation
                </label>
              </div>
            ) : null}

            {commandId === "answer_generation" ? (
              <div className="mt-4 space-y-4">
                <fieldset>
                  <legend className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                    Systems
                  </legend>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {meta.systems.map((item) => (
                      <label
                        key={item.id}
                        className="flex items-center gap-2 text-sm font-bold"
                      >
                        <input
                          type="checkbox"
                          checked={systems.includes(item.id)}
                          onChange={() => toggle(item.id, systems, setSystems)}
                          className="h-4 w-4 accent-moss"
                        />
                        {item.name}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <label className="block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                  Output directory
                  <input
                    list="report-run-directories"
                    value={outputDir}
                    onChange={(event) => setOutputDir(event.target.value)}
                    className={`${inputClass} mt-2`}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm font-bold">
                  <input
                    type="checkbox"
                    checked={resumeGeneration}
                    onChange={(event) =>
                      setResumeGeneration(event.target.checked)
                    }
                    className="h-4 w-4 accent-moss"
                  />
                  Resume các sample hợp lệ đã có
                </label>
              </div>
            ) : null}

            {commandId === "bottleneck_analysis" ? (
              <label className="mt-4 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                Arm
                <select
                  value={bottleneckArm}
                  onChange={(event) => setBottleneckArm(event.target.value)}
                  className={`${inputClass} mt-2`}
                >
                  <option value="z">Thực tế (baseline)</option>
                  <option value="x">Intake hoàn hảo</option>
                  <option value="w">RAG hoàn hảo</option>
                  <option value="y">Generator mạnh (API)</option>
                </select>
              </label>
            ) : null}

            {["llm_scoring", "build_report", "quality_gate", "trust_audit"].includes(
              commandId,
            ) ? (
              <label className="mt-4 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                Run directory
                <input
                  list="report-run-directories"
                  value={runDir}
                  onChange={(event) => setRunDir(event.target.value)}
                  className={`${inputClass} mt-2`}
                />
              </label>
            ) : null}

            {commandId === "llm_scoring" ? (
              <fieldset className="mt-4">
                <legend className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                  Pairwise comparisons
                </legend>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {pairOptions.map((item) => (
                    <label
                      key={item}
                      className="flex items-center gap-2 text-sm font-bold"
                    >
                      <input
                        type="checkbox"
                        checked={pairs.includes(item)}
                        onChange={() => toggle(item, pairs, setPairs)}
                        className="h-4 w-4 accent-moss"
                      />
                      {item
                        .split(":")
                        .map((id) => systemLabel(meta.systems, id))
                        .join(" ↔ ")}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}

            {commandId === "trust_audit" ? (
              <div className="mt-4 space-y-4">
                <label className="block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                  Repro subset
                  <input
                    type="number"
                    min={0}
                    max={200}
                    value={reproSubset}
                    onChange={(event) => setReproSubset(event.target.value)}
                    className={`${inputClass} mt-2`}
                  />
                  <span className="mt-1 block normal-case tracking-normal text-ink/40">
                    0 = bỏ qua rerun tốn thời gian; 20 = validation đầy đủ.
                  </span>
                </label>
                <label className="flex items-center gap-2 text-sm font-bold">
                  <input
                    type="checkbox"
                    checked={strictValidation}
                    onChange={(event) => setStrictValidation(event.target.checked)}
                    className="h-4 w-4 accent-moss"
                  />
                  Strict: WARN/SKIPPED cũng làm job exit non-zero
                </label>
              </div>
            ) : null}

            <Button
              className="mt-5 w-full"
              variant={commandId === "llm_scoring" ? "secondary" : "primary"}
              disabled={submitting}
              onClick={() => void submit()}
            >
              {submitting ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Play size={17} />
              )}
              {submitting ? "Đang tạo job…" : `Run ${selectedCommand.label}`}
            </Button>
          </Card>

          <Card className="overflow-hidden">
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-center justify-between">
                <h2 className="font-black">Job registry</h2>
                <Pill tone="neutral">{jobs.length}</Pill>
              </div>
            </div>
            <div className="max-h-[520px] divide-y divide-line overflow-y-auto">
              {jobs.map((job) => (
                <button
                  key={job.jobId}
                  onClick={() => {
                    setSelectedJobId(job.jobId);
                    window.history.replaceState(null, "", `/runs?job=${job.jobId}`);
                  }}
                  className={`flex w-full items-center gap-3 px-5 py-4 text-left transition hover:bg-canvas/60 ${
                    job.jobId === selectedJobId ? "bg-lime/15" : ""
                  }`}
                >
                  <span
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
                      job.status === "running"
                        ? "bg-[#1d2b31] text-[#83b8cf]"
                        : job.status === "stopping"
                          ? "bg-[#332719] text-[#e8b96d]"
                        : job.status === "succeeded"
                          ? "bg-moss/10 text-moss"
                          : "bg-ember/10 text-ember"
                    }`}
                  >
                    {["running", "stopping"].includes(job.status) ? (
                      <LoaderCircle className="animate-spin" size={16} />
                    ) : job.status === "succeeded" ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <XCircle size={16} />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-black">
                      {commandLabel(job.commandId)}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink/42">
                      {formatStarted(job.startedAt)} · PID {job.pid}
                    </span>
                  </span>
                  <ChevronRight size={15} className="text-ink/25" />
                </button>
              ))}
              {!jobs.length ? (
                <div className="p-5">
                  <EmptyState
                    title="Registry trống"
                    description="Tạo job đầu tiên bằng form phía trên."
                  />
                </div>
              ) : null}
            </div>
          </Card>
        </div>

        <div className="min-w-0 space-y-5">
          <Card className="overflow-hidden">
            <div className="flex flex-col gap-4 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <TerminalSquare size={18} />
                  <h2 className="font-black">
                    {selectedJob ? commandLabel(selectedJob.commandId) : "Live console"}
                  </h2>
                  {selectedJob ? (
                    <Pill tone={jobTone(selectedJob.status)}>
                      {selectedJob.status}
                    </Pill>
                  ) : null}
                </div>
                {selectedJob ? (
                  <p className="mt-1 truncate font-mono text-[11px] text-ink/42">
                    {selectedJob.command}
                  </p>
                ) : null}
              </div>
              {selectedJob ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-bold text-ink/45">
                    <Clock3 size={14} />
                    {formatDuration(elapsedMs)}
                  </span>
                  {["running", "stopping"].includes(selectedJob.status) ? (
                    <Button
                      variant="danger"
                      className="px-3 py-2"
                      disabled={
                        selectedJob.status === "stopping" ||
                        killingJobId === selectedJob.jobId
                      }
                      onClick={() => void killSelected()}
                    >
                      {selectedJob.status === "stopping" ? (
                        <LoaderCircle className="animate-spin" size={15} />
                      ) : (
                        <CircleStop size={15} />
                      )}
                      {selectedJob.status === "stopping" ? "Stopping…" : "Kill"}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>

            {selectedJob?.commandId === "full_evaluation" ? (
              <RunAllMonitor job={selectedJob} log={log} progress={progress} />
            ) : null}

            <div className="flex flex-col gap-3 border-b border-line bg-canvas/45 px-5 py-3 sm:flex-row sm:items-center">
              <label className="relative min-w-0 flex-1">
                <Filter
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35"
                />
                <input
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Filter regex: FAIL|FALLBACK|s3"
                  className={`${inputClass} py-2 pl-9 font-mono text-xs`}
                />
              </label>
              <button
                type="button"
                aria-pressed={markerOnly}
                onClick={() => setMarkerOnly((value) => !value)}
                className={`rounded-lg px-3 py-2 text-xs font-black transition ${
                  markerOnly
                    ? "bg-clay text-white"
                    : "border border-line bg-[#211f1b] text-ink/55 hover:text-ink"
                }`}
              >
                Chỉ hiện marker
              </button>
              <label className="flex items-center gap-2 whitespace-nowrap text-xs font-bold text-ink/55">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(event) => setAutoScroll(event.target.checked)}
                  className="h-4 w-4 accent-moss"
                />
                Auto-scroll
              </label>
              <button
                onClick={() => setLog("")}
                className="inline-flex items-center gap-1.5 text-xs font-black text-ink/50 hover:text-ink"
              >
                <RotateCcw size={13} /> Clear view
              </button>
            </div>

            {visibleLines.error ? (
              <div className="bg-ember/10 px-5 py-2 text-xs font-bold text-ember">
                Regex không hợp lệ: {visibleLines.error}
              </div>
            ) : null}

            <div
              ref={consoleRef}
              className="scrollbar-thin h-[540px] overflow-auto bg-[#111815] p-4 font-mono text-[12px] leading-5"
            >
              {selectedJob ? (
                visibleLines.lines.map((line, index) => (
                  <div
                    key={`${index}-${line.slice(0, 24)}`}
                    className={`min-h-5 whitespace-pre-wrap break-words ${lineClass(line)}`}
                  >
                    {line || " "}
                  </div>
                ))
              ) : (
                <div className="grid h-full place-items-center text-center text-[#86918b]">
                  <div>
                    <TerminalSquare className="mx-auto mb-3" size={30} />
                    Chọn hoặc tạo một job để bắt đầu tail log.
                  </div>
                </div>
              )}
            </div>
          </Card>

          {selectedJob?.commandId === "trust_audit" && validationWatch ? (
            <Card className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                    Validation summary
                  </p>
                  <h2 className="mt-1 text-xl font-black">
                    {validationWatch.summary.verdict ?? "UNKNOWN"}
                  </h2>
                  <p className="mt-1 font-mono text-[11px] text-ink/42">
                    {validationWatch.path}
                  </p>
                </div>
                <Pill tone={validationTone(validationWatch.summary.verdict)}>
                  {validationWatch.summary.conflicts_n ?? 0} conflicts
                </Pill>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {(validationWatch.summary.per_check ?? []).map((check) => (
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
              {(validationWatch.summary.confidence_notes ?? []).length ? (
                <ul className="mt-4 list-disc space-y-1 pl-5 text-xs leading-5 text-ink/50">
                  {validationWatch.summary.confidence_notes?.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ) : null}

          {progress.length && selectedJob?.commandId !== "full_evaluation" ? (
            <Card className="p-5">
              <GenerationProgressBars progress={progress} />
            </Card>
          ) : selectedJob &&
            selectedJob.commandId !== "full_evaluation" &&
            ["running", "stopping"].includes(selectedJob.status) ? (
            <Card className="flex items-center gap-3 p-4 text-sm font-bold text-ink/55">
              <LoaderCircle className="animate-spin text-moss" size={18} />
              {selectedJob.status === "stopping"
                ? "Đang dừng toàn bộ process tree…"
                : "Job đang chạy. Intake và RAG hiển thị tiến độ trong console; bước sinh câu trả lời có thêm thanh tiến độ theo cấu hình."}
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}
