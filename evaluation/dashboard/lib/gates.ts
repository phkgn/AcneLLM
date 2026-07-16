import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";
import { asNumber, asRecord, readJsonFile } from "./files";
import { EVALUATION_ROOT, REPORTS_ROOT } from "./paths";

export interface GateCheck {
  section: string;
  metric: string;
  threshold: number;
  value: number | null;
  status: "pass" | "fail" | "missing";
  source: string;
  system?: string;
  comparison: "min" | "max" | "equal";
}

async function loadGateConfig(): Promise<Record<string, Record<string, number>>> {
  try {
    return (yaml.load(
      await fs.readFile(
        path.join(EVALUATION_ROOT, "configs", "gate.yaml"),
        "utf8",
      ),
    ) ?? {}) as Record<string, Record<string, number>>;
  } catch {
    return {};
  }
}

async function latestRetrievalSummary(): Promise<{
  path: string;
  data: Record<string, unknown>;
} | null> {
  const root = path.join(REPORTS_ROOT, "retrieval");
  try {
    const dirs = await fs.readdir(root, { withFileTypes: true });
    const candidates = await Promise.all(
      dirs
        .filter((entry) => entry.isDirectory())
        .map(async (entry) => {
          const summaryPath = path.join(root, entry.name, "summary.json");
          const stat = await fs.stat(summaryPath).catch(() => null);
          if (!stat) return null;
          return {
            summaryPath,
            mtime: stat.mtimeMs,
            data:
              (await readJsonFile<Record<string, unknown>>(summaryPath)) ?? {},
          };
        }),
    );
    const sorted = candidates
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .sort((a, b) => b.mtime - a.mtime);
    const latest =
      sorted.find((item) => item.data.raw_query !== true) ?? sorted[0];
    if (!latest) return null;
    return {
      path: path.relative(EVALUATION_ROOT, latest.summaryPath).replaceAll("\\", "/"),
      data: latest.data,
    };
  } catch {
    return null;
  }
}

function findNumberDeep(value: unknown, keys: string[]): number | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  for (const key of keys) {
    const direct = asNumber(record[key]);
    if (direct !== null) return direct;
  }
  for (const child of Object.values(record)) {
    const found = findNumberDeep(child, keys);
    if (found !== null) return found;
  }
  return null;
}

function normalizerMicroF1(value: unknown): number | null {
  const report = asRecord(value);
  const multiLabel = asRecord(report.multi_label);
  const lesionStrict = asRecord(multiLabel.lesion_strict);
  return asNumber(lesionStrict.micro_f1);
}

function compare(
  value: number | null,
  threshold: number,
  comparison: GateCheck["comparison"],
): GateCheck["status"] {
  if (value === null) return "missing";
  if (comparison === "max") return value <= threshold ? "pass" : "fail";
  if (comparison === "equal") return value === threshold ? "pass" : "fail";
  return value >= threshold ? "pass" : "fail";
}

function addCheck(
  checks: GateCheck[],
  section: string,
  metric: string,
  threshold: number,
  value: number | null,
  source: string,
  comparison: GateCheck["comparison"] = "min",
  system?: string,
) {
  checks.push({
    section,
    metric,
    threshold,
    value,
    source,
    comparison,
    system,
    status: compare(value, threshold, comparison),
  });
}

export async function evaluateGates(experiment = "main_2x2_t3") {
  const config = await loadGateConfig();
  const reportPath = path.join(REPORTS_ROOT, experiment, "report.json");
  const report =
    (await readJsonFile<Record<string, unknown>>(reportPath)) ?? {};
  const systems = asRecord(report.systems);
  const productionSystem = asRecord(systems.s3);
  const generationSource = `reports/${experiment}/report.json`;
  const retrieval = await latestRetrievalSummary();
  const retrievalModes = asRecord(retrieval?.data.modes);
  const preferredRetrieval = asRecord(retrievalModes.hybrid_mmr_rerank);
  const retrievalProduction = Object.keys(preferredRetrieval).length
    ? preferredRetrieval
    : asRecord(Object.values(retrievalModes)[0]);

  const intent = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "unit", "intent_router", "report.json"),
  );
  const normalizerSummary = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "unit", "normalizer", "summary.json"),
  );
  const normalizerReport = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "unit", "normalizer", "report.json"),
  );
  const normalizerValue =
    normalizerMicroF1(normalizerSummary) ??
    normalizerMicroF1(normalizerReport) ??
    findNumberDeep(normalizerSummary, ["micro_f1"]) ??
    findNumberDeep(normalizerReport, ["micro_f1"]);
  const guardrails = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "unit", "guardrails", "report.json"),
  );
  const planner = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "unit", "query_planner", "report.json"),
  );

  const checks: GateCheck[] = [];
  for (const [metric, threshold] of Object.entries(config.retrieval ?? {})) {
    addCheck(
      checks,
      "retrieval",
      metric,
      threshold,
      asNumber(retrievalProduction[metric]),
      retrieval?.path ?? "reports/retrieval/<latest>/summary.json",
    );
  }
  const generationMapping: Record<string, string> = {
    parse_success_rate: "parse_success_rate",
    citation_valid_rate: "citation_valid_rate",
  };
  for (const [metric, threshold] of Object.entries(config.generation ?? {})) {
    addCheck(
      checks,
      "generation",
      metric,
      threshold,
      asNumber(productionSystem[generationMapping[metric] ?? metric]),
      generationSource,
      "min",
      "s3",
    );
  }

  const errorPareto = Array.isArray(productionSystem.error_pareto)
    ? productionSystem.error_pareto
    : [];
  const unsafeCount = errorPareto.reduce((total, item) => {
    if (
      Array.isArray(item) &&
      item[0] === "E15_unsafe_recommendation" &&
      typeof item[1] === "number"
    ) {
      return total + item[1];
    }
    return total;
  }, 0);
  for (const [metric, threshold] of Object.entries(config.safety ?? {})) {
    addCheck(
      checks,
      "safety",
      metric,
      threshold,
      Object.keys(productionSystem).length ? unsafeCount : null,
      generationSource,
      "equal",
      "s3",
    );
  }

  const injection = asRecord(guardrails?.injection_detection);
  const scope = asRecord(guardrails?.scope_check);
  const unitValues: Record<string, { value: number | null; source: string }> = {
    intent_macro_f1: {
      value: asNumber(intent?.intent_macro_f1),
      source: "reports/unit/intent_router/report.json",
    },
    intent_reject_recall: {
      value: asNumber(intent?.reject_recall),
      source: "reports/unit/intent_router/report.json",
    },
    normalizer_micro_f1: {
      value: normalizerValue,
      source:
        normalizerMicroF1(normalizerSummary) !== null
          ? "reports/unit/normalizer/summary.json"
          : "reports/unit/normalizer/report.json",
    },
    guardrails_injection_recall: {
      value: asNumber(injection.tpr) ?? asNumber(injection.recall),
      source: "reports/unit/guardrails/report.json",
    },
    guardrails_out_of_scope_fnr_max: {
      value: asNumber(scope.fnr),
      source: "reports/unit/guardrails/report.json",
    },
    planner_all_ok_rate: {
      value: asNumber(planner?.all_ok_rate),
      source: "reports/unit/query_planner/report.json",
    },
  };
  for (const [metric, threshold] of Object.entries(config.unit ?? {})) {
    const item = unitValues[metric] ?? {
      value: null,
      source: "reports/unit/",
    };
    addCheck(
      checks,
      "unit",
      metric,
      threshold,
      item.value,
      item.source,
      metric.endsWith("_max") ? "max" : "min",
    );
  }

  return {
    checks,
    summary: {
      pass: checks.filter((check) => check.status === "pass").length,
      fail: checks.filter((check) => check.status === "fail").length,
      missing: checks.filter((check) => check.status === "missing").length,
    },
  };
}
