"use client";

import {
  CheckCircle2,
  ChevronRight,
  CircleStop,
  Clock3,
  Filter,
  LoaderCircle,
  Play,
  RotateCcw,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  PRELIMINARY_LIMIT_MAX,
  PRELIMINARY_LIMIT_MIN,
  isValidPreliminaryLimitInput,
  parsePreliminaryLimit,
} from "@/lib/preliminary";
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
  tier: string;
  description: string;
}> = [
  {
    id: "run_all",
    label: "Run all",
    tier: "T1 → report",
    description: "Orchestrator đầy đủ, có smoke/skip/dataset override.",
  },
  {
    id: "preliminary_d2",
    label: "Quick preliminary D2",
    tier: "T3 → Judge → Report",
    description:
      "Preset 30–140 mẫu D2 synthetic-only, tự tạo run riêng và không chạy D8/gate.",
  },
  {
    id: "tests",
    label: "Harness tests",
    tier: "pytest",
    description: "Chạy evaluation/tests -q.",
  },
  {
    id: "t1_normalizer",
    label: "Normalizer",
    tier: "T1",
    description: "Delegate sang normalizer eval legacy đã kiểm chứng.",
  },
  {
    id: "t1_intent",
    label: "Intent router",
    tier: "T1",
    description: "Accuracy, macro-F1 và reject recall.",
  },
  {
    id: "t1_planner",
    label: "Query planner",
    tier: "T1",
    description: "Property checks P1–P6 trên query construction.",
  },
  {
    id: "t1_guardrails",
    label: "Guardrails",
    tier: "T1",
    description: "Injection và out-of-scope detection.",
  },
  {
    id: "t2_retrieval",
    label: "Retrieval",
    tier: "T2",
    description: "Ablation sparse/dense/hybrid/rerank/MMR.",
  },
  {
    id: "t3_generation",
    label: "Generation S0–S4",
    tier: "T3",
    description: "Batch experiment dài, chọn output riêng và resume khi cần.",
  },
  {
    id: "judge",
    label: "LLM judge",
    tier: "Judge · $",
    description: "Pointwise, faithfulness và pairwise; phát sinh chi phí API.",
  },
  {
    id: "report",
    label: "Build report",
    tier: "Analysis",
    description: "Tổng hợp metric, paired comparisons và Pareto lỗi.",
  },
  {
    id: "check_gate",
    label: "Check regression gates",
    tier: "Gate",
    description: "Chạy gate.yaml qua harness và cập nhật gate_check.json.",
  },
  {
    id: "validation_loop",
    label: "Validation loop",
    tier: "Trust audit",
    description: "Audit data/runtime/invariants/judge, conflicts và reproducibility.",
  },
];

const retrievalModes = [
  "sparse",
  "dense",
  "hybrid",
  "hybrid_rerank",
  "hybrid_mmr_rerank",
];
const skipSteps = ["t1", "t2", "t3", "judge", "report", "gate"];
const pairOptions = ["s0:s1", "s0:s2", "s1:s3", "s2:s3"];

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

function lineClass(line: string) {
  if (/FALLBACK DETECTED|FAIL|ERROR|Traceback/i.test(line)) {
    return "text-[#ff9278]";
  }
  if (/⚠|WARN/i.test(line)) return "text-[#ffd166]";
  if (/\bOK\b|✓|passed/i.test(line)) return "text-[#cde76c]";
  if (/^\[dashboard\]|^\[command\]/.test(line)) return "text-[#80bfff]";
  return "text-[#d8ded9]";
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

export function RunsClient() {
  const [meta, setMeta] = useState<MetaResponse>({ datasets: [], systems: [] });
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [commandId, setCommandId] = useState<CommandId>("t1_intent");
  const [limit, setLimit] = useState("5");
  const [preliminaryLimit, setPreliminaryLimit] = useState(
    String(PRELIMINARY_LIMIT_MAX),
  );
  const [dataset, setDataset] = useState(
    "evaluation/datasets/v1/d1_dev_seed.jsonl",
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
  const [submitting, setSubmitting] = useState(false);
  const [killingJobId, setKillingJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [log, setLog] = useState("");
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [validationWatch, setValidationWatch] =
    useState<ValidationWatch | null>(null);
  const preliminaryLimitValid = isValidPreliminaryLimitInput(preliminaryLimit);
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
    selectedJob?.commandId === "validation_loop" ? selectedJob.jobId : null;
  const validationJobStartedAt =
    selectedJob?.commandId === "validation_loop" ? selectedJob.startedAt : null;

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
      !["t3_generation", "run_all", "preliminary_d2"].includes(
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
        : "evaluation/datasets/v1/d2_test.jsonl";
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
    const lines = log.split(/\r?\n/).map(stripAnsi);
    if (!filter) return { lines, error: "" };
    try {
      const regex = new RegExp(filter, "i");
      return { lines: lines.filter((line) => regex.test(line)), error: "" };
    } catch (regexError) {
      return { lines, error: (regexError as Error).message };
    }
  }, [filter, log]);

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
        "run_all",
        "preliminary_d2",
        "tests",
        "t1_normalizer",
        "report",
        "check_gate",
        "validation_loop",
      ].includes(commandId)
    ) {
      args.limit = parsedLimit;
    }
    if (commandId === "run_all") {
      args.smoke = smoke;
      args.skip = skip;
      args.dataset = dataset;
      args.yes = yes;
    }
    if (commandId === "preliminary_d2") {
      args.limit = parsePreliminaryLimit(preliminaryLimit);
    }
    if (commandId === "t2_retrieval") {
      args.modes = modes;
      args.rawQuery = rawQuery;
    }
    if (commandId === "t3_generation") {
      args.systems = systems;
      args.outDir = outputDir;
      args.resume = resumeGeneration;
    }
    if (commandId === "judge") {
      args.dataset = dataset;
      args.pairs = pairs;
      args.runDir = runDir;
    }
    if (commandId === "report") {
      args.dataset = dataset;
      args.runDir = runDir;
    }
    if (commandId === "check_gate") args.runDir = runDir;
    if (commandId === "validation_loop") {
      args.dataset = dataset;
      args.runDir = runDir;
      args.reproSubset = Number(reproSubset) || 0;
      args.strict = strictValidation;
    }
    return args;
  }

  async function submit() {
    if (commandId === "preliminary_d2" && !preliminaryLimitValid) {
      setError(
        `Quick Run limit phải là số nguyên từ ${PRELIMINARY_LIMIT_MIN} đến ${PRELIMINARY_LIMIT_MAX}.`,
      );
      return;
    }
    if (
      ["judge", "preliminary_d2"].includes(commandId) &&
      !window.confirm(
        commandId === "preliminary_d2"
          ? `Preset này chạy ${parsePreliminaryLimit(preliminaryLimit)} mẫu D2 qua S0–S4 rồi gọi OpenAI GPT-5 mini Judge và tạo report. Có thể phát sinh chi phí API. Tiếp tục?`
          : "OpenAI GPT-5 mini Judge sẽ dùng API key và có thể phát sinh chi phí. Tiếp tục?",
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
      if (commandId === "t3_generation") setRunDir(outputDir);
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
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                  Command
                </p>
                <h2 className="mt-1 text-xl font-black">Cấu hình run</h2>
              </div>
              <Pill tone={commandId === "judge" ? "warn" : "neutral"}>
                {selectedCommand.tier}
              </Pill>
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
            {commandId === "preliminary_d2" ? (
              <>
                <div className="mt-4 rounded-xl border border-[#514027] bg-[#332719]/70 px-3 py-3 text-xs leading-5 text-[#e8b96d]">
                  D2 × {preliminaryLimitValid ? preliminaryLimit : "—"}, S0–S4,
                  bốn pairwise comparisons. Artifact được ghi vào run directory mới
                  cùng PROVISIONAL_NOTICE.md. Không chạy D8, gate hoặc judge
                  calibration.
                </div>
                <label className="mt-4 block text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                  Số mẫu ({PRELIMINARY_LIMIT_MIN}–{PRELIMINARY_LIMIT_MAX})
                  <input
                    aria-label="Quick Run sample limit"
                    type="number"
                    min={PRELIMINARY_LIMIT_MIN}
                    max={PRELIMINARY_LIMIT_MAX}
                    step={1}
                    value={preliminaryLimit}
                    onChange={(event) => setPreliminaryLimit(event.target.value)}
                    className={`${inputClass} mt-2`}
                  />
                  {!preliminaryLimitValid ? (
                    <span className="mt-1 block normal-case tracking-normal text-ember">
                      Nhập số nguyên từ {PRELIMINARY_LIMIT_MIN} đến{" "}
                      {PRELIMINARY_LIMIT_MAX}.
                    </span>
                  ) : null}
                </label>
              </>
            ) : null}
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
              "run_all",
              "preliminary_d2",
              "tests",
              "t1_normalizer",
              "report",
              "check_gate",
              "validation_loop",
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

            {["run_all", "judge", "report", "validation_loop"].includes(commandId) ? (
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

            {commandId === "run_all" ? (
              <div className="mt-4 space-y-4">
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 text-sm font-bold">
                    <input
                      type="checkbox"
                      checked={smoke}
                      onChange={(event) => setSmoke(event.target.checked)}
                      className="h-4 w-4 accent-moss"
                    />
                    Smoke
                  </label>
                  <label className="flex items-center gap-2 text-sm font-bold">
                    <input
                      type="checkbox"
                      checked={yes}
                      onChange={(event) => setYes(event.target.checked)}
                      className="h-4 w-4 accent-moss"
                    />
                    --yes
                  </label>
                </div>
                <fieldset>
                  <legend className="text-xs font-black uppercase tracking-[0.12em] text-ink/50">
                    Skip steps
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
                        {item}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </div>
            ) : null}

            {commandId === "t2_retrieval" ? (
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

            {commandId === "t3_generation" ? (
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
                        {item.id.toUpperCase()} · {item.name}
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

            {["judge", "report", "check_gate", "validation_loop"].includes(
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

            {commandId === "judge" ? (
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
                      {item}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}

            {commandId === "validation_loop" ? (
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
              variant={commandId === "judge" ? "secondary" : "primary"}
              disabled={
                submitting ||
                (commandId === "preliminary_d2" && !preliminaryLimitValid)
              }
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
                      {job.commandId}
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
                    {selectedJob ? selectedJob.commandId : "Live console"}
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

          {selectedJob?.commandId === "validation_loop" && validationWatch ? (
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

          {progress.length ? (
            <Card className="p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                    T3 progress
                  </p>
                  <h2 className="mt-1 text-xl font-black">Per-system completion</h2>
                </div>
                <Pill tone="info">SSE watched</Pill>
              </div>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                {progress.map((item) => (
                  <div
                    key={item.system}
                    className="rounded-2xl border border-line bg-canvas/45 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-black uppercase">{item.system}</p>
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
            </Card>
          ) : selectedJob &&
            ["running", "stopping"].includes(selectedJob.status) ? (
            <Card className="flex items-center gap-3 p-4 text-sm font-bold text-ink/55">
              <LoaderCircle className="animate-spin text-moss" size={18} />
              {selectedJob.status === "stopping"
                ? "Đang dừng toàn bộ process tree…"
                : "Job đang chạy. Với T1/T2, tiến độ chi tiết được hiển thị trực tiếp trong console; T3 có thêm progress bar per system."}
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}
