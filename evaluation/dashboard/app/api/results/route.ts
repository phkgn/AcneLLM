import path from "node:path";
import { NextResponse } from "next/server";
import { readJsonFile } from "@/lib/files";
import { evaluateGates } from "@/lib/gates";
import { REPORTS_ROOT, assertSafeName } from "@/lib/paths";
import { latestRetrievalResult, readUnitReports } from "@/lib/results";
import { latestValidationSummary } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const experiment = assertSafeName(
      url.searchParams.get("experiment") ?? "main_2x2_t3",
      "Experiment",
    );
    const runDir = path.join(REPORTS_ROOT, experiment);
    const [report, runMeta, units, retrieval, gates, validation] = await Promise.all([
      readJsonFile<Record<string, unknown>>(path.join(runDir, "report.json")),
      readJsonFile<Record<string, unknown>>(path.join(runDir, "run_meta.json")),
      readUnitReports(),
      latestRetrievalResult(),
      evaluateGates(experiment),
      latestValidationSummary(),
    ]);
    return NextResponse.json({
      experiment,
      report,
      runMeta,
      units,
      retrieval,
      gates,
      validation,
    });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
