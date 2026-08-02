import path from "node:path";
import { NextResponse } from "next/server";
import { countNonEmptyLines, readJsonl } from "@/lib/files";
import {
  EVALUATION_ROOT,
  REPORTS_ROOT,
  assertSafeName,
  resolveEvaluationPath,
  toEvaluationRelative,
} from "@/lib/paths";
import { loadSystemLabels } from "@/lib/systems";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const VALID_SYSTEM = /^s[0-4]$/;

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const experiment = assertSafeName(
      url.searchParams.get("experiment") ?? "main_2x2_t3",
      "Experiment",
    );
    const datasetRaw =
      url.searchParams.get("dataset") ??
      "evaluation/datasets/v1/answer_quality_test.jsonl";
    const datasetPath = resolveEvaluationPath(datasetRaw);
    const relativeDataset = path.relative(
      path.join(EVALUATION_ROOT, "datasets"),
      datasetPath,
    );
    if (
      relativeDataset.startsWith("..") ||
      path.isAbsolute(relativeDataset) ||
      path.extname(datasetPath).toLowerCase() !== ".jsonl"
    ) {
      throw new Error("Dataset không hợp lệ.");
    }
    const systemsRaw = url.searchParams.get("systems") ?? "s0,s1,s2,s3,s4";
    const systems = systemsRaw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!systems.length || !systems.every((item) => VALID_SYSTEM.test(item))) {
      throw new Error("Systems không hợp lệ.");
    }
    const limitRaw = url.searchParams.get("limit");
    const limit = limitRaw ? Number(limitRaw) : null;
    const datasetRows = await countNonEmptyLines(datasetPath);
    const total =
      limit && Number.isInteger(limit) && limit > 0
        ? Math.min(datasetRows, limit)
        : datasetRows;

    const systemLabels = loadSystemLabels();
    const progress = await Promise.all(
      systems.map(async (system) => {
        const resultPath = path.join(
          REPORTS_ROOT,
          experiment,
          `${system}.results.jsonl`,
        );
        const rows = await readJsonl(resultPath);
        const durations = rows
          .map((row) => {
            const timings =
              row.timings_ms &&
              typeof row.timings_ms === "object" &&
              !Array.isArray(row.timings_ms)
                ? (row.timings_ms as Record<string, unknown>)
                : {};
            return typeof timings.total === "number" ? timings.total : null;
          })
          .filter((value): value is number => value !== null);
        const averageMs = durations.length
          ? durations.reduce((sum, value) => sum + value, 0) / durations.length
          : null;
        const completed = rows.length;
        const remaining = Math.max(total - completed, 0);
        return {
          system,
          systemLabel: systemLabels[system] ?? system,
          completed,
          total,
          percent: total ? Math.min(100, (completed / total) * 100) : 0,
          averageMs,
          etaMs: averageMs === null ? null : averageMs * remaining,
          ok: rows.filter((row) => row.ok === true).length,
          failed: rows.filter((row) => row.ok !== true).length,
          watchPath: toEvaluationRelative(resultPath),
        };
      }),
    );
    return NextResponse.json({ experiment, dataset: datasetRaw, progress });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
