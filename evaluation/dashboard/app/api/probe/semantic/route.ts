import { spawn } from "node:child_process";
import { NextResponse } from "next/server";
import { buildCommand } from "@/lib/commands";
import { REPO_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Cold start loads the sentence embedder each run; keep the cap generous.
const PROBE_TIMEOUT_MS = 180_000;
const MAX_OUTPUT_BYTES = 1_000_000;

interface ProbeRun {
  exitCode: number | null;
  stdout: string;
  stderrTail: string;
  timedOut: boolean;
  spawnError: string | null;
}

function runProbe(executable: string, argv: string[]): Promise<ProbeRun> {
  return new Promise((resolve) => {
    const child = spawn(executable, argv, {
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

    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let spawnError: string | null = null;
    const timer = setTimeout(() => {
      timedOut = true;
      if (child.pid) {
        if (process.platform === "win32") {
          spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
            shell: false,
            windowsHide: true,
          });
        } else {
          try {
            child.kill("SIGTERM");
          } catch {
            // Process already gone.
          }
        }
      }
    }, PROBE_TIMEOUT_MS);

    child.stdout.on("data", (chunk: Buffer) => {
      if (stdout.length < MAX_OUTPUT_BYTES) stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      if (stderr.length < MAX_OUTPUT_BYTES) stderr += chunk.toString("utf8");
    });
    child.once("error", (error) => {
      spawnError = error.message;
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      const stderrLines = stderr
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      resolve({
        exitCode: code,
        stdout,
        stderrTail: stderrLines.slice(-5).join("\n"),
        timedOut,
        spawnError,
      });
    });
  });
}

function extractJsonLine(stdout: string): Record<string, unknown> | null {
  const lines = stdout.split(/\r?\n/).filter((line) => line.trim());
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index].trim();
    if (!line.startsWith("{")) continue;
    try {
      const parsed = JSON.parse(line) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // Older progress output can mimic JSON; keep scanning upwards.
    }
  }
  return null;
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Body phải là JSON." }, { status: 400 });
  }

  let built;
  try {
    built = buildCommand("probe_semantic", body);
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }

  const startedAt = Date.now();
  const run = await runProbe(built.executable, built.argv);
  const durationMs = Date.now() - startedAt;

  if (run.timedOut) {
    return NextResponse.json(
      {
        error: `Probe quá ${Math.round(PROBE_TIMEOUT_MS / 1000)}s — có thể embedder đang tải model lần đầu, thử lại.`,
        command: built.display,
      },
      { status: 504 },
    );
  }
  if (run.spawnError) {
    return NextResponse.json(
      { error: `Không spawn được Python: ${run.spawnError}`, command: built.display },
      { status: 500 },
    );
  }

  const payload = extractJsonLine(run.stdout);
  if (!payload) {
    return NextResponse.json(
      {
        error: `Probe không trả JSON (exit=${String(run.exitCode)}). ${run.stderrTail}`,
        command: built.display,
      },
      { status: 502 },
    );
  }
  if (typeof payload.error === "string" || run.exitCode !== 0) {
    return NextResponse.json(
      {
        error:
          typeof payload.error === "string"
            ? payload.error
            : `Probe thoát với exit=${String(run.exitCode)}. ${run.stderrTail}`,
        command: built.display,
      },
      { status: 502 },
    );
  }

  return NextResponse.json({
    result: payload,
    command: built.display,
    durationMs,
  });
}
