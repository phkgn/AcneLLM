"use client";

import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleStop,
  Clock3,
  Database,
  Play,
  RefreshCw,
  TestTube2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { JobRecord } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
  formatBytes,
} from "./ui";

type StatusResponse = {
  checkedAt: string;
  ready: boolean;
  checks: Array<{
    id: string;
    label: string;
    ok: boolean;
    detail: string;
    fix: string;
  }>;
};

type Gate = {
  section: string;
  metric: string;
  threshold: number;
  value: number | null;
  status: "pass" | "fail" | "missing";
  source: string;
  system?: string;
};

type OverviewResponse = {
  lastRun: {
    started?: string;
    finished?: string;
    results?: Record<string, string>;
  } | null;
  gates: {
    checks: Gate[];
    summary: { pass: number; fail: number; missing: number };
  };
  judgeCacheBytes: number;
};

function elapsed(startedAt: string) {
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export function DashboardClient() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [, tick] = useState(0);

  const refresh = useCallback(async () => {
    const [statusRes, overviewRes, jobsRes] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/api/overview", { cache: "no-store" }),
      fetch("/api/jobs", { cache: "no-store" }),
    ]);
    if (statusRes.ok) setStatus((await statusRes.json()) as StatusResponse);
    if (overviewRes.ok) setOverview((await overviewRes.json()) as OverviewResponse);
    if (jobsRes.ok) {
      const body = (await jobsRes.json()) as { jobs: JobRecord[] };
      setJobs(body.jobs);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const poll = setInterval(() => void refresh(), 1500);
    const clock = setInterval(() => tick((value) => value + 1), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [refresh]);

  async function launch(
    commandId: string,
    args: Record<string, unknown> = {},
  ) {
    setBusy(commandId);
    setError("");
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commandId, args }),
      });
      const body = (await response.json()) as {
        job?: JobRecord;
        error?: string;
      };
      if (!response.ok || !body.job) throw new Error(body.error ?? "Không thể tạo job.");
      window.location.href = `/runs?job=${body.job.jobId}`;
    } catch (launchError) {
      setError((launchError as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function kill(jobId: string) {
    setBusy(jobId);
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
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  const runningJobs = jobs.filter((job) =>
    ["running", "stopping"].includes(job.status),
  );
  const failedChecks = status?.checks.filter((check) => !check.ok) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Evaluation harness"
        title="Control room cho mọi eval run"
        description="Kiểm tra dependency, chạy harness từ whitelist, theo dõi process và đọc regression gate mà không chạm production chat UI."
        actions={
          <Button variant="ghost" onClick={() => void refresh()}>
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

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden">
          <div className="border-b border-line px-5 py-5 sm:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                  Preflight
                </p>
                <h2 className="mt-1 text-xl font-black">Runtime readiness</h2>
              </div>
              <Pill tone={status?.ready ? "good" : "warn"}>
                {status
                  ? status.ready
                    ? "Ready"
                    : `${failedChecks.length} cần xử lý`
                  : "Checking"}
              </Pill>
            </div>
          </div>
          <div className="divide-y divide-line">
            {status?.checks.map((check) => (
              <div
                key={check.id}
                className="grid gap-3 px-5 py-4 sm:grid-cols-[28px_1fr_auto] sm:px-6"
              >
                <span
                  className={`grid h-7 w-7 place-items-center rounded-full ${
                    check.ok ? "bg-moss/10 text-moss" : "bg-ember/10 text-ember"
                  }`}
                >
                  {check.ok ? <Check size={15} /> : <X size={15} />}
                </span>
                <div>
                  <p className="text-sm font-black">{check.label}</p>
                  <p className="mt-0.5 text-xs leading-5 text-ink/48">
                    {check.detail}
                  </p>
                </div>
                {!check.ok ? (
                  <code className="max-w-md self-center overflow-x-auto rounded-lg bg-deep px-2.5 py-1.5 text-[10px] text-[#ef9a7d]">
                    {check.fix}
                  </code>
                ) : null}
              </div>
            ))}
            {!status ? (
              <div className="px-6 py-10 text-center text-sm font-bold text-ink/40">
                Đang kiểm tra Ollama, KB và datasets…
              </div>
            ) : null}
          </div>
        </Card>

        <div className="space-y-5">
          <Card className="p-5 sm:p-6">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
              Quick launch
            </p>
            <h2 className="mt-1 text-xl font-black">Bắt đầu một run</h2>
            <div className="mt-5 grid gap-3">
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() =>
                  void launch("run_all", {
                    smoke: true,
                    dataset: "evaluation/datasets/v1/d1_dev_seed.jsonl",
                  })
                }
              >
                <TestTube2 size={17} />
                Smoke run all
              </Button>
              <Button
                disabled={busy !== null}
                onClick={() => void launch("run_all")}
              >
                <Play size={17} />
                Run all full
              </Button>
              <Button
                variant="ghost"
                disabled={busy !== null}
                onClick={() => void launch("tests")}
              >
                <Check size={17} />
                Run harness tests
              </Button>
            </div>
            <p className="mt-4 text-xs leading-5 text-ink/45">
              Judge có thể phát sinh chi phí API; thao tác đó chỉ có trong trang Runs
              và luôn có cảnh báo xác nhận.
            </p>
          </Card>

          <Card className="p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                  Active processes
                </p>
                <h2 className="mt-1 text-xl font-black">Jobs đang chạy</h2>
              </div>
              <Pill tone={runningJobs.length ? "info" : "neutral"}>
                {runningJobs.length}
              </Pill>
            </div>
            <div className="mt-4 space-y-3">
              {runningJobs.map((job) => (
                <div
                  key={job.jobId}
                  className="rounded-2xl border border-line bg-canvas/45 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-black">{job.commandId}</p>
                      <p className="mt-1 flex items-center gap-1.5 text-xs text-ink/45">
                        <Clock3 size={13} />
                        {elapsed(job.startedAt)} · PID {job.pid}
                      </p>
                    </div>
                    <span
                      className={`mt-1 h-2.5 w-2.5 shrink-0 animate-pulse-soft rounded-full ${
                        job.status === "stopping" ? "bg-[#d8a34f]" : "bg-moss"
                      }`}
                    />
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Link
                      href={`/runs?job=${job.jobId}`}
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-deep px-3 py-2 text-xs font-black text-ink ring-1 ring-line"
                    >
                      Xem log <ArrowRight size={14} />
                    </Link>
                    <button
                      onClick={() => void kill(job.jobId)}
                      disabled={busy === job.jobId || job.status === "stopping"}
                      className="grid h-9 w-9 place-items-center rounded-xl bg-ember/10 text-ember hover:bg-ember hover:text-white disabled:opacity-50"
                      aria-label={`Kill ${job.commandId}`}
                    >
                      {job.status === "stopping" ? (
                        <RefreshCw className="animate-spin" size={16} />
                      ) : (
                        <CircleStop size={16} />
                      )}
                    </button>
                  </div>
                </div>
              ))}
              {!runningJobs.length ? (
                <EmptyState
                  title="Không có job đang chạy"
                  description="Các process đã hoàn tất vẫn được giữ trong registry và có thể xem lại tại trang Runs."
                />
              ) : null}
            </div>
          </Card>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
                Regression gates
              </p>
              <h2 className="mt-1 text-xl font-black">Pass / fail theo gate.yaml</h2>
            </div>
            {overview ? (
              <div className="flex gap-2">
                <Pill tone="good">{overview.gates.summary.pass} pass</Pill>
                <Pill tone={overview.gates.summary.fail ? "bad" : "neutral"}>
                  {overview.gates.summary.fail} fail
                </Pill>
                <Pill tone="neutral">{overview.gates.summary.missing} missing</Pill>
              </div>
            ) : null}
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {overview?.gates.checks.map((gate) => (
              <div
                key={`${gate.section}-${gate.metric}`}
                className="rounded-2xl border border-line bg-canvas/45 p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-black uppercase tracking-[0.12em] text-ink/42">
                    {gate.section}
                  </p>
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
                <p className="mt-1 text-xs text-ink/48">
                  value {gate.value ?? "—"} · threshold {gate.threshold}
                </p>
              </div>
            ))}
            {!overview?.gates.checks.length ? (
              <div className="sm:col-span-2 xl:col-span-3">
                <EmptyState
                  title="Chưa có gate data"
                  description="Chạy T1/T2/T3 và report để dashboard có metric thật để so với gate."
                />
              </div>
            ) : null}
          </div>
        </Card>

        <Card className="p-5 sm:p-6">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-ink/40">
            Last orchestrator run
          </p>
          <h2 className="mt-1 text-xl font-black">run_all_last.json</h2>
          {overview?.lastRun ? (
            <>
              <div className="mt-5 space-y-2">
                {Object.entries(overview.lastRun.results ?? {}).map(([step, value]) => {
                  const ok = value === "OK";
                  return (
                    <div
                      key={step}
                      className="flex items-center justify-between gap-3 rounded-xl bg-canvas/55 px-3 py-2.5"
                    >
                      <span className="text-sm font-bold">{step}</span>
                      <Pill tone={ok ? "good" : "bad"}>{value}</Pill>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-xs leading-5 text-ink/45">
                Finished:{" "}
                {overview.lastRun.finished
                  ? new Date(overview.lastRun.finished).toLocaleString("vi-VN")
                  : "—"}
              </p>
            </>
          ) : (
            <div className="mt-5">
              <EmptyState
                title="Chưa có orchestrator run"
                description="File evaluation/reports/run_all_last.json sẽ xuất hiện sau lần chạy run_all đầu tiên."
              />
            </div>
          )}
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-line bg-[#211f1b] px-3 py-3 text-xs font-bold text-ink/55">
            <Database size={15} />
            Judge cache: {formatBytes(overview?.judgeCacheBytes ?? 0)}
          </div>
          {failedChecks.length ? (
            <div className="mt-3 flex gap-2 rounded-xl bg-[#332719] px-3 py-3 text-xs leading-5 text-[#e8b96d]">
              <AlertTriangle className="mt-0.5 shrink-0" size={15} />
              Full run hiện sẽ dừng ở preflight nếu các dependency bắt buộc chưa được
              xử lý.
            </div>
          ) : null}
        </Card>
      </div>
    </>
  );
}
