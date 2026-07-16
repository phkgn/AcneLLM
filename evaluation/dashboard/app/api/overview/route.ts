import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { readJsonFile } from "@/lib/files";
import { evaluateGates } from "@/lib/gates";
import { REPORTS_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const lastRun = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "run_all_last.json"),
  );
  const judgeCacheBytes = await fs
    .stat(path.join(REPORTS_ROOT, "judge_cache.sqlite"))
    .then((stat) => stat.size)
    .catch(() => 0);
  return NextResponse.json({
    lastRun,
    gates: await evaluateGates(),
    judgeCacheBytes,
  });
}
