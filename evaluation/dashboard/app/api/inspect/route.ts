import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";
import { NextResponse } from "next/server";
import { readJsonFile, readJsonl } from "@/lib/files";
import { sampleErrorCodes } from "@/lib/inspect";
import {
  EVALUATION_ROOT,
  REPO_ROOT,
  REPORTS_ROOT,
  assertSafeName,
} from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Row = Record<string, unknown>;

async function datasetForRun(
  experiment: string,
  runMeta: Row | null,
): Promise<string | null> {
  const experimentMeta =
    runMeta?.experiment &&
    typeof runMeta.experiment === "object" &&
    !Array.isArray(runMeta.experiment)
      ? (runMeta.experiment as Row)
      : {};
  if (typeof experimentMeta.dataset === "string") {
    return experimentMeta.dataset;
  }
  if (typeof runMeta?.dataset === "string") return runMeta.dataset;

  const configsDir = path.join(EVALUATION_ROOT, "configs", "experiments");
  try {
    const files = await fs.readdir(configsDir);
    for (const file of files.filter((name) => name.endsWith(".yaml"))) {
      const config = (yaml.load(
        await fs.readFile(path.join(configsDir, file), "utf8"),
      ) ?? {}) as Row;
      if (config.name === experiment && typeof config.dataset === "string") {
        return config.dataset;
      }
    }
  } catch {
    return null;
  }
  return null;
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const experiment = assertSafeName(
      url.searchParams.get("experiment") ?? "main_2x2_t3",
      "Experiment",
    );
    const system = assertSafeName(
      url.searchParams.get("system") ?? "s3",
      "System",
    );
    if (!/^s[0-4]$/.test(system)) throw new Error("System không hợp lệ.");
    const runDir = path.join(REPORTS_ROOT, experiment);
    const runMeta = await readJsonFile<Row>(path.join(runDir, "run_meta.json"));
    const datasetRelative = await datasetForRun(experiment, runMeta);
    const datasetRows = datasetRelative
      ? await readJsonl(path.join(REPO_ROOT, datasetRelative))
      : [];
    const samples = new Map(
      datasetRows.map((row) => [String(row.sample_id ?? ""), row]),
    );
    const results = await readJsonl(
      path.join(runDir, `${system}.results.jsonl`),
    );
    const judged = new Map(
      (
        await readJsonl(path.join(runDir, `${system}.judged.jsonl`))
      ).map((row) => [String(row.sample_id ?? ""), row]),
    );
    const availableSystems = (
      await fs.readdir(runDir).catch(() => [])
    )
      .filter((file) => /^s[0-4]\.results\.jsonl$/.test(file))
      .map((file) => file.split(".")[0])
      .sort();

    const sampleId = url.searchParams.get("sampleId");
    if (sampleId) {
      const result = results.find((row) => row.sample_id === sampleId) ?? null;
      const sample = samples.get(sampleId) ?? null;
      const compareSystem = url.searchParams.get("compare");
      let compare = null;
      if (compareSystem && /^s[0-4]$/.test(compareSystem)) {
        compare =
          (
            await readJsonl(
              path.join(runDir, `${compareSystem}.results.jsonl`),
            )
          ).find((row) => row.sample_id === sampleId) ?? null;
      }
      return NextResponse.json({
        experiment,
        system,
        dataset: datasetRelative,
        availableSystems,
        result,
        sample,
        judged: judged.get(sampleId) ?? null,
        errorCodes:
          result && sample ? sampleErrorCodes(result, sample) : [],
        compareSystem,
        compare,
      });
    }

    const query = (url.searchParams.get("query") ?? "").trim().toLocaleLowerCase("vi");
    const page = Math.max(1, Number(url.searchParams.get("page") ?? 1) || 1);
    const pageSize = 50;
    const enriched = results.map((result) => {
      const id = String(result.sample_id ?? "");
      const sample = samples.get(id) ?? {};
      const errorCodes = sampleErrorCodes(result, sample);
      return {
        sampleId: id,
        query: String(sample.user_query ?? ""),
        ok: result.ok === true,
        error: result.error ?? null,
        modelName: result.model_name ?? null,
        latencyMs:
          result.timings_ms &&
          typeof result.timings_ms === "object" &&
          !Array.isArray(result.timings_ms)
            ? (result.timings_ms as Row).total ?? null
            : null,
        answerPreview: String(result.answer ?? "").slice(0, 220),
        errorCodes,
        flagged:
          result.ok !== true ||
          errorCodes.includes("E22_fallback") ||
          /FALLBACK/i.test(String(result.error ?? "")),
      };
    });
    const filtered = query
      ? enriched.filter((row) =>
          [row.sampleId, row.query, row.answerPreview]
            .join("\n")
            .toLocaleLowerCase("vi")
            .includes(query),
        )
      : enriched;
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const safePage = Math.min(page, totalPages);
    return NextResponse.json({
      experiment,
      system,
      dataset: datasetRelative,
      availableSystems,
      total: filtered.length,
      page: safePage,
      pageSize,
      totalPages,
      rows: filtered.slice((safePage - 1) * pageSize, safePage * pageSize),
    });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
