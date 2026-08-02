import assert from "node:assert/strict";
import test from "node:test";
import {
  checkGateRunFlags,
  generationOutputFlags,
} from "../lib/command-flags.ts";
import { COMMAND_IDS } from "../lib/command-ids.ts";
import { buildCommand } from "../lib/commands.ts";

test("generation flags honor an isolated output directory without forcing resume", () => {
  assert.deepEqual(
    generationOutputFlags("evaluation/reports/qa_1case", false),
    ["--out-dir", "evaluation/reports/qa_1case"],
  );
});

test("generation flags append resume only when explicitly enabled", () => {
  assert.deepEqual(
    generationOutputFlags("evaluation/reports/qa_1case", true),
    ["--out-dir", "evaluation/reports/qa_1case", "--resume"],
  );
});

test("quality gate command remains in the dashboard whitelist", () => {
  assert.equal(COMMAND_IDS.includes("quality_gate"), true);
  assert.deepEqual(
    checkGateRunFlags("evaluation/reports/qa_1case"),
    ["--run-dir", "evaluation/reports/qa_1case"],
  );
});

test("full evaluation always receives a validated output directory", () => {
  const explicit = buildCommand("full_evaluation", {
    outDir: "evaluation/reports/thesis_command_test",
    smoke: true,
    yes: true,
  });
  assert.deepEqual(explicit.argv, [
    "-m",
    "evaluation.full_evaluation",
    "--out",
    "evaluation/reports/thesis_command_test",
    "--smoke",
    "--yes",
  ]);
  assert.equal(
    explicit.normalizedArgs.outDir,
    "evaluation/reports/thesis_command_test",
  );

  const generated = buildCommand("full_evaluation", {});
  assert.match(
    String(generated.normalizedArgs.outDir),
    /^evaluation\/reports\/thesis_\d{8}T\d{6}_\d{3}Z$/,
  );
  assert.deepEqual(
    generated.argv.slice(0, 4),
    ["-m", "evaluation.full_evaluation", "--out", generated.normalizedArgs.outDir],
  );
});

test("figure generators are fixed Python modules with validated flags", () => {
  const kb = buildCommand("figures_kb", { sample: 8000, pdf: true });
  assert.deepEqual(kb.argv, [
    "-m",
    "evaluation.analysis.figures_kb",
    "--sample",
    "8000",
    "--pdf",
  ]);
  assert.equal(COMMAND_IDS.includes("figures_eval"), true);
  assert.equal(COMMAND_IDS.includes("figures_usage"), true);

  const all = buildCommand("figures_all", {
    sample: 8000,
    runDir: "evaluation/reports/main_2x2_t3",
    pdf: true,
  });
  assert.deepEqual(all.argv, [
    "-m",
    "evaluation.generate_figures",
    "--sample",
    "8000",
    "--run-dir",
    "evaluation/reports/main_2x2_t3",
    "--pdf",
  ]);
  assert.equal(COMMAND_IDS.includes("figures_all"), true);
});

test("LLM scoring command delegates provider and pointwise model to Python settings", () => {
  const command = buildCommand("llm_scoring", {
    runDir: "evaluation/reports/main_2x2_t3",
    dataset: "evaluation/datasets/v1/answer_quality_test.jsonl",
  });
  assert.deepEqual(command.argv, [
    "-m",
    "evaluation.judges.run_judge",
    "--run-dir",
    "evaluation/reports/main_2x2_t3",
    "--dataset",
    "evaluation/datasets/v1/answer_quality_test.jsonl",
    "--workers",
    "4",
  ]);
  assert.equal("judgeProvider" in command.normalizedArgs, false);
  assert.equal("judgeModel" in command.normalizedArgs, false);
  assert.equal("faithfulnessModel" in command.normalizedArgs, false);
  assert.equal(command.normalizedArgs.judgeWorkers, 4);
});

test("intake and four bottleneck configurations are dashboard commands", () => {
  assert.equal(COMMAND_IDS.includes("intake_eval"), true);
  assert.equal(COMMAND_IDS.includes("bottleneck_analysis"), true);
  assert.deepEqual(buildCommand("intake_eval", { limit: 5 }).argv, [
    "scripts/eval_unified_intake.py",
    "--limit",
    "5",
  ]);

  for (const arm of ["z", "x", "y", "w"]) {
    const command = buildCommand("bottleneck_analysis", { arm, limit: 5 });
    assert.deepEqual(command.argv, [
      "scripts/eval_bottleneck.py",
      "--arm",
      arm,
      "--limit",
      "5",
    ]);
    assert.equal(command.normalizedArgs.arm, arm);
  }
  assert.throws(
    () => buildCommand("bottleneck_analysis", { arm: "invalid" }),
    /Arm chỉ nhận z\|x\|y\|w/,
  );
});
