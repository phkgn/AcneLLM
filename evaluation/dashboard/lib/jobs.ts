import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { buildCommand } from "./commands";
import { JOBS_FILE, LOGS_ROOT, REPO_ROOT, toEvaluationRelative } from "./paths";
import type { JobRecord } from "./types";

interface RegistryState {
  loaded: boolean;
  jobs: Map<string, JobRecord>;
}

declare global {
  // eslint-disable-next-line no-var
  var __acneEvalJobs: RegistryState | undefined;
}

const state: RegistryState =
  globalThis.__acneEvalJobs ??
  {
    loaded: false,
    jobs: new Map<string, JobRecord>(),
  };

globalThis.__acneEvalJobs = state;

function pidIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function persist(): Promise<void> {
  await fsp.mkdir(path.dirname(JOBS_FILE), { recursive: true });
  const records = [...state.jobs.values()].sort((a, b) =>
    b.startedAt.localeCompare(a.startedAt),
  );
  await fsp.writeFile(JOBS_FILE, JSON.stringify(records, null, 2), "utf8");
}

async function ensureLoaded(): Promise<void> {
  if (state.loaded) return;
  state.loaded = true;
  try {
    const parsed = JSON.parse(await fsp.readFile(JOBS_FILE, "utf8")) as JobRecord[];
    for (const job of parsed) {
      if (job.status === "stopping") {
        if (pidIsAlive(job.pid)) {
          job.status = "running";
          job.signal = null;
        } else {
          job.status = "killed";
          job.finishedAt = job.finishedAt ?? new Date().toISOString();
        }
      } else if (job.status === "running" && !pidIsAlive(job.pid)) {
        job.status = "exited";
        job.finishedAt = job.finishedAt ?? new Date().toISOString();
      }
      state.jobs.set(job.jobId, job);
    }
    await persist();
  } catch {
    // First run: the registry file does not exist yet.
  }
}

function updateFinishedJob(
  jobId: string,
  exitCode: number | null,
  signal: NodeJS.Signals | null,
): void {
  const job = state.jobs.get(jobId);
  if (!job || !["running", "stopping"].includes(job.status)) return;
  job.exitCode = exitCode;
  job.signal = signal;
  job.finishedAt = new Date().toISOString();
  job.status =
    job.status === "stopping"
      ? "killed"
      : exitCode === 0
        ? "succeeded"
        : "failed";
  void persist();
}

export async function listJobs(): Promise<JobRecord[]> {
  await ensureLoaded();
  let changed = false;
  for (const job of state.jobs.values()) {
    if (
      (job.status === "running" || job.status === "stopping") &&
      !pidIsAlive(job.pid)
    ) {
      job.status = job.status === "stopping" ? "killed" : "exited";
      job.finishedAt = job.finishedAt ?? new Date().toISOString();
      changed = true;
    }
  }
  if (changed) await persist();
  return [...state.jobs.values()].sort((a, b) =>
    b.startedAt.localeCompare(a.startedAt),
  );
}

export async function getJob(jobId: string): Promise<JobRecord | null> {
  await ensureLoaded();
  return state.jobs.get(jobId) ?? null;
}

export async function startJob(
  commandId: unknown,
  args: unknown,
): Promise<JobRecord> {
  await ensureLoaded();
  const built = buildCommand(commandId, args);
  await fsp.mkdir(LOGS_ROOT, { recursive: true });
  const jobId = `${Date.now().toString(36)}-${crypto.randomBytes(4).toString("hex")}`;
  const absoluteLogFile = path.join(LOGS_ROOT, `${jobId}.log`);
  const logStream = fs.createWriteStream(absoluteLogFile, {
    flags: "a",
    encoding: "utf8",
  });
  logStream.write(
    `[dashboard] ${new Date().toISOString()}\n[command] ${built.display}\n\n`,
  );

  const child = spawn(built.executable, built.argv, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PYTHONIOENCODING: "utf-8",
      PYTHONUNBUFFERED: "1",
      FORCE_COLOR: "0",
      NO_COLOR: "1",
      PY_COLORS: "0",
      TERM: "dumb",
    },
    shell: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const job: JobRecord = {
    jobId,
    pid: child.pid ?? -1,
    commandId: built.commandId,
    command: built.display,
    argv: built.argv,
    args: built.normalizedArgs,
    startedAt: new Date().toISOString(),
    status: "running",
    exitCode: null,
    signal: null,
    logFile: toEvaluationRelative(absoluteLogFile),
  };
  state.jobs.set(jobId, job);
  child.stdout.pipe(logStream, { end: false });
  child.stderr.pipe(logStream, { end: false });
  child.once("error", (error) => {
    logStream.write(`\n[dashboard] spawn error: ${error.message}\n`);
    updateFinishedJob(jobId, 1, null);
    logStream.end();
  });
  child.once("close", (code, signal) => {
    logStream.write(
      `\n[dashboard] process finished: exit=${String(code)} signal=${String(signal)}\n`,
    );
    updateFinishedJob(jobId, code, signal);
    logStream.end();
  });
  await persist();
  return job;
}

function taskkill(pid: number): Promise<{ code: number | null; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn("taskkill", ["/pid", String(pid), "/T", "/F"], {
      shell: false,
      windowsHide: true,
    });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.once("error", reject);
    child.once("close", (code) => resolve({ code, stderr }));
  });
}

export async function killJob(jobId: string): Promise<JobRecord> {
  await ensureLoaded();
  const job = state.jobs.get(jobId);
  if (!job) throw new Error("Không tìm thấy job.");
  if (job.status === "stopping") return job;
  if (job.status !== "running") return job;

  job.status = "stopping";
  job.signal =
    process.platform === "win32" ? "TASKKILL_REQUESTED" : "SIGTERM_REQUESTED";
  await persist();

  try {
    if (pidIsAlive(job.pid)) {
      if (process.platform === "win32") {
        const result = await taskkill(job.pid);
        if (result.code !== 0 && pidIsAlive(job.pid)) {
          throw new Error(result.stderr.trim() || "taskkill thất bại.");
        }
      } else {
        process.kill(job.pid, "SIGTERM");
      }
    }
    job.status = "killed";
    job.exitCode = null;
    job.signal = process.platform === "win32" ? "TASKKILL" : "SIGTERM";
    job.finishedAt = new Date().toISOString();
    await persist();
    return job;
  } catch (error) {
    if (!pidIsAlive(job.pid)) {
      job.status = "killed";
      job.exitCode = null;
      job.signal = process.platform === "win32" ? "TASKKILL" : "SIGTERM";
      job.finishedAt = new Date().toISOString();
      await persist();
      return job;
    }
    job.status = "running";
    job.signal = null;
    await persist();
    throw error;
  }
}
