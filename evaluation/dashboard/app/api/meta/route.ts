import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import {
  listDatasets,
  listExperiments,
  listReportRuns,
  listSystems,
} from "@/lib/catalog";
import { summarizeJudgeCalibration } from "@/lib/judge-calibration";
import { REPORTS_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const cachePath = path.join(REPORTS_ROOT, "judge_cache.sqlite");
  const calibrationPath = path.join(REPORTS_ROOT, "judge_bias_tests.json");
  const judgeCacheBytes = await fs
    .stat(cachePath)
    .then((stat) => stat.size)
    .catch(() => 0);
  const [datasets, experiments, systems, reportRuns, calibrationArtifact] =
    await Promise.all([
    listDatasets(),
    listExperiments(),
    listSystems(),
    listReportRuns(),
    fs
      .readFile(calibrationPath, "utf8")
      .then((raw) => JSON.parse(raw) as unknown)
      .catch(() => null),
  ]);
  return NextResponse.json({
    datasets,
    experiments,
    systems,
    reportRuns,
    judgeCacheBytes,
    judgeCalibration: summarizeJudgeCalibration(calibrationArtifact),
  });
}
