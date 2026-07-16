import fs from "node:fs";
import path from "node:path";
import {
  EVALUATION_ROOT,
  REPO_ROOT,
  isPathInside,
  resolveEvaluationPath,
  toRepoRelative,
} from "./paths";
import { checkGateRunFlags, t3OutputFlags } from "./command-flags";
import { COMMAND_IDS } from "./command-ids";
import type { CommandId } from "./types";

const FORBIDDEN = /[;&|`$><\r\n]/;
const SYSTEM_IDS = new Set(["s0", "s1", "s2", "s3", "s4"]);
const RETRIEVAL_MODES = new Set([
  "sparse",
  "dense",
  "hybrid",
  "hybrid_rerank",
  "hybrid_mmr_rerank",
]);
const SKIP_STEPS = new Set(["t1", "t2", "t3", "judge", "report", "gate"]);

export interface BuiltCommand {
  commandId: CommandId;
  executable: string;
  argv: string[];
  display: string;
  normalizedArgs: Record<string, unknown>;
}

function pythonExecutable(): string {
  const windowsVenv = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const unixVenv = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(windowsVenv)) return windowsVenv;
  if (fs.existsSync(unixVenv)) return unixVenv;
  return process.platform === "win32" ? "python" : "python3";
}

function assertCleanString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim() || FORBIDDEN.test(value)) {
    throw new Error(`${label} không hợp lệ.`);
  }
  return value.trim();
}

function optionalLimit(value: unknown): number | null {
  if (value === undefined || value === null || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 100_000) {
    throw new Error("Limit phải là số nguyên từ 1 đến 100000.");
  }
  return parsed;
}

function optionalReproSubset(value: unknown): number {
  if (value === undefined || value === null || value === "") return 0;
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 200) {
    throw new Error("Repro subset phải là số nguyên từ 0 đến 200.");
  }
  return parsed;
}

function reportRunDir(value: unknown): string {
  const raw = value
    ? assertCleanString(value, "Run directory")
    : "evaluation/reports/main_2x2_t3";
  const resolved = resolveEvaluationPath(raw);
  const reportsRoot = path.join(EVALUATION_ROOT, "reports");
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    throw new Error("Run directory phải là thư mục có thật trong evaluation/reports/.");
  }
  const realResolved = fs.realpathSync(resolved);
  const realReportsRoot = fs.realpathSync(reportsRoot);
  if (!isPathInside(realReportsRoot, realResolved)) {
    throw new Error("Run directory phải nằm trong evaluation/reports/.");
  }
  return toRepoRelative(resolved);
}

function outputRunDir(value: unknown): string {
  const raw = value
    ? assertCleanString(value, "Output directory")
    : "evaluation/reports/main_2x2_t3";
  const resolved = resolveEvaluationPath(raw);
  const reportsRoot = path.join(EVALUATION_ROOT, "reports");
  const relativeToReports = path.relative(reportsRoot, resolved);
  if (
    !relativeToReports ||
    relativeToReports.startsWith("..") ||
    path.isAbsolute(relativeToReports)
  ) {
    throw new Error("Output directory phải nằm trong evaluation/reports/.");
  }
  if (fs.existsSync(resolved) && !fs.statSync(resolved).isDirectory()) {
    throw new Error("Output directory phải là một thư mục.");
  }

  let existing = resolved;
  while (!fs.existsSync(existing)) {
    const parent = path.dirname(existing);
    if (parent === existing) break;
    existing = parent;
  }
  const realExisting = fs.realpathSync(existing);
  const realReportsRoot = fs.realpathSync(reportsRoot);
  if (!isPathInside(realReportsRoot, realExisting)) {
    throw new Error("Output directory phải nằm trong evaluation/reports/.");
  }
  return toRepoRelative(resolved);
}

function stringList(value: unknown, allowed: Set<string>, label: string): string[] {
  if (value === undefined || value === null || value === "") return [];
  const items = Array.isArray(value)
    ? value
    : assertCleanString(value, label).split(",");
  const normalized = items.map((item) => String(item).trim()).filter(Boolean);
  if (!normalized.every((item) => allowed.has(item))) {
    throw new Error(`${label} chứa giá trị ngoài whitelist.`);
  }
  return [...new Set(normalized)];
}

function datasetPath(value: unknown, fallback?: string): string {
  const raw = value ? assertCleanString(value, "Dataset") : fallback;
  if (!raw) throw new Error("Bạn phải chọn dataset.");
  const resolved = resolveEvaluationPath(raw);
  const datasetRoot = path.join(EVALUATION_ROOT, "datasets");
  if (!fs.existsSync(resolved)) {
    throw new Error("Dataset phải là file .jsonl có thật trong evaluation/datasets/.");
  }
  const realResolved = fs.realpathSync(resolved);
  const realDatasetRoot = fs.realpathSync(datasetRoot);
  const relativeToDatasets = path.relative(datasetRoot, resolved);
  if (
    relativeToDatasets.startsWith("..") ||
    path.isAbsolute(relativeToDatasets) ||
    path.extname(resolved).toLowerCase() !== ".jsonl" ||
    !isPathInside(realDatasetRoot, realResolved)
  ) {
    throw new Error("Dataset phải là file .jsonl có thật trong evaluation/datasets/.");
  }
  return toRepoRelative(resolved);
}

function pairList(value: unknown): string[] {
  if (value === undefined || value === null || value === "") return [];
  const raw = Array.isArray(value)
    ? value.map(String)
    : assertCleanString(value, "Pairs").split(",");
  const pairs = raw.map((item) => item.trim()).filter(Boolean);
  for (const pair of pairs) {
    const [a, b, extra] = pair.split(":");
    if (extra || !SYSTEM_IDS.has(a) || !SYSTEM_IDS.has(b) || a === b) {
      throw new Error("Pairs chỉ nhận dạng s0:s1,s1:s3.");
    }
  }
  return [...new Set(pairs)];
}

function quoteForDisplay(value: string): string {
  return /\s/.test(value) ? JSON.stringify(value) : value;
}

export function buildCommand(commandIdRaw: unknown, argsRaw: unknown): BuiltCommand {
  if (
    typeof commandIdRaw !== "string" ||
    !COMMAND_IDS.includes(commandIdRaw as CommandId)
  ) {
    throw new Error("CommandId không nằm trong whitelist.");
  }
  const commandId = commandIdRaw as CommandId;
  const args =
    argsRaw && typeof argsRaw === "object" && !Array.isArray(argsRaw)
      ? (argsRaw as Record<string, unknown>)
      : {};
  const py = pythonExecutable();
  const argv: string[] = [];
  const normalizedArgs: Record<string, unknown> = {};
  const limit = optionalLimit(args.limit);

  switch (commandId) {
    case "run_all": {
      argv.push("-m", "evaluation.run_all");
      if (args.smoke === true) {
        argv.push("--smoke");
        normalizedArgs.smoke = true;
      }
      const skip = stringList(args.skip, SKIP_STEPS, "Skip");
      if (skip.length) {
        argv.push("--skip", skip.join(","));
        normalizedArgs.skip = skip;
      }
      if (args.dataset) {
        const dataset = datasetPath(args.dataset);
        argv.push("--dataset", dataset);
        normalizedArgs.dataset = dataset;
      }
      if (args.yes === true) {
        argv.push("--yes");
        normalizedArgs.yes = true;
      }
      break;
    }
    case "t1_normalizer":
      argv.push("-m", "evaluation.unit.eval_normalizer");
      break;
    case "t1_intent":
      argv.push(
        "-m",
        "evaluation.unit.eval_intent_router",
        "--dataset",
        "evaluation/datasets/v1/t1_intent_seed.jsonl",
      );
      break;
    case "t1_planner":
      argv.push(
        "-m",
        "evaluation.unit.eval_query_planner",
        "--dataset",
        "evaluation/datasets/v1/t1_intent_seed.jsonl",
      );
      break;
    case "t1_guardrails":
      argv.push(
        "-m",
        "evaluation.unit.eval_guardrails",
        "--dataset",
        "evaluation/datasets/v1/t1_guardrails_seed.jsonl",
      );
      break;
    case "t2_retrieval": {
      argv.push(
        "-m",
        "evaluation.runners.run_retrieval",
        "--dataset",
        "evaluation/datasets/v1/d8_qrels_seed.jsonl",
      );
      const modes = stringList(args.modes, RETRIEVAL_MODES, "Modes");
      if (modes.length) {
        argv.push("--modes", modes.join(","));
        normalizedArgs.modes = modes;
      }
      if (args.rawQuery === true) {
        argv.push("--raw-query");
        normalizedArgs.rawQuery = true;
      }
      break;
    }
    case "t3_generation": {
      argv.push(
        "-m",
        "evaluation.runners.run_experiment",
        "--experiment",
        "evaluation/configs/experiments/main_2x2.yaml",
      );
      const systems = stringList(args.systems, SYSTEM_IDS, "Systems");
      if (systems.length) {
        argv.push("--systems", systems.join(","));
        normalizedArgs.systems = systems;
      }
      const outDir = outputRunDir(args.outDir);
      const resume = args.resume !== false;
      argv.push(...t3OutputFlags(outDir, resume));
      normalizedArgs.outDir = outDir;
      normalizedArgs.resume = resume;
      break;
    }
    case "judge": {
      const dataset = datasetPath(
        args.dataset,
        "evaluation/datasets/v1/d1_dev_seed.jsonl",
      );
      const runDir = reportRunDir(args.runDir);
      argv.push(
        "-m",
        "evaluation.judges.run_judge",
        "--run-dir",
        runDir,
        "--dataset",
        dataset,
      );
      normalizedArgs.dataset = dataset;
      normalizedArgs.runDir = runDir;
      const pairs = pairList(args.pairs);
      if (pairs.length) {
        argv.push("--pairs", pairs.join(","));
        normalizedArgs.pairs = pairs;
      }
      break;
    }
    case "report": {
      const dataset = datasetPath(
        args.dataset,
        "evaluation/datasets/v1/d1_dev_seed.jsonl",
      );
      const runDir = reportRunDir(args.runDir);
      argv.push(
        "-m",
        "evaluation.analysis.report",
        "--run-dir",
        runDir,
        "--dataset",
        dataset,
      );
      normalizedArgs.dataset = dataset;
      normalizedArgs.runDir = runDir;
      break;
    }
    case "check_gate": {
      const runDir = reportRunDir(args.runDir);
      argv.push(
        "-m",
        "evaluation.analysis.check_gate",
        ...checkGateRunFlags(runDir),
      );
      normalizedArgs.runDir = runDir;
      break;
    }
    case "validation_loop": {
      const dataset = datasetPath(
        args.dataset,
        "evaluation/datasets/v1/d1_dev_seed.jsonl",
      );
      const runDir = reportRunDir(args.runDir);
      const reproSubset = optionalReproSubset(args.reproSubset);
      argv.push(
        "-m",
        "evaluation.validate.loop",
        "--run-dir",
        runDir,
        "--dataset",
        dataset,
        "--repro-subset",
        String(reproSubset),
      );
      normalizedArgs.dataset = dataset;
      normalizedArgs.runDir = runDir;
      normalizedArgs.reproSubset = reproSubset;
      if (args.strict === true) {
        argv.push("--strict");
        normalizedArgs.strict = true;
      }
      break;
    }
    case "tests":
      argv.push("-m", "pytest", "evaluation/tests", "-q");
      break;
  }

  if (
    limit !== null &&
    commandId !== "run_all" &&
    commandId !== "t1_normalizer" &&
    commandId !== "tests" &&
    commandId !== "report" &&
    commandId !== "check_gate" &&
    commandId !== "validation_loop"
  ) {
    argv.push("--limit", String(limit));
    normalizedArgs.limit = limit;
  }

  const displayExecutable = path.isAbsolute(py) ? toRepoRelative(py) : py;
  return {
    commandId,
    executable: py,
    argv,
    display: [displayExecutable, ...argv].map(quoteForDisplay).join(" "),
    normalizedArgs,
  };
}
