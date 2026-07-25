import assert from "node:assert/strict";
import test from "node:test";
import {
  checkGateRunFlags,
  t3OutputFlags,
} from "../lib/command-flags.ts";
import { COMMAND_IDS } from "../lib/command-ids.ts";
import { buildCommand } from "../lib/commands.ts";

test("T3 flags honor an isolated output directory without forcing resume", () => {
  assert.deepEqual(
    t3OutputFlags("evaluation/reports/qa_1case", false),
    ["--out-dir", "evaluation/reports/qa_1case"],
  );
});

test("T3 flags append resume only when explicitly enabled", () => {
  assert.deepEqual(
    t3OutputFlags("evaluation/reports/qa_1case", true),
    ["--out-dir", "evaluation/reports/qa_1case", "--resume"],
  );
});

test("documented check_gate command remains in the dashboard whitelist", () => {
  assert.equal(COMMAND_IDS.includes("check_gate"), true);
  assert.deepEqual(
    checkGateRunFlags("evaluation/reports/qa_1case"),
    ["--run-dir", "evaluation/reports/qa_1case"],
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

test("preliminary D2 preset uses an isolated run and the standard pipeline wrapper", () => {
  const command = buildCommand("preliminary_d2", {
    outDir: "evaluation/reports/prelim_d2_test",
  });
  assert.deepEqual(command.argv, [
    "evaluation/dashboard/scripts/run_preliminary_d2.py",
    "--out-dir",
    "evaluation/reports/prelim_d2_test",
    "--limit",
    "140",
  ]);
  assert.deepEqual(command.normalizedArgs, {
    outDir: "evaluation/reports/prelim_d2_test",
    dataset: "evaluation/datasets/v1/d2_test.jsonl",
    systems: ["s0", "s1", "s2", "s3", "s4"],
    pairs: ["s0:s1", "s0:s2", "s1:s3", "s2:s3"],
    limit: 140,
    provisional: true,
    faithfulnessModel: "gpt-5-nano-2025-08-07",
    judgeWorkers: 4,
  });
  assert.equal(COMMAND_IDS.includes("preliminary_d2"), true);
});

test("preliminary D2 accepts a configurable limit from 30 through 140", () => {
  for (const limit of [30, 85, 140]) {
    const command = buildCommand("preliminary_d2", {
      outDir: `evaluation/reports/prelim_d2_${limit}`,
      limit,
    });
    assert.equal(command.normalizedArgs.limit, limit);
    assert.deepEqual(command.argv.slice(-2), ["--limit", String(limit)]);
  }
});

test("preliminary D2 rejects limits outside 30 through 140", () => {
  for (const limit of [29, 141, 30.5, "abc"]) {
    assert.throws(
      () => buildCommand("preliminary_d2", { limit }),
      /Quick Run limit phải là số nguyên từ 30 đến 140/,
    );
  }
});

test("probe_semantic builds a spawn-safe argv with optional overrides", () => {
  const command = buildCommand("probe_semantic", {
    text: "da mình mụn viêm nhiều nên dùng gì?",
    k: 5,
    oos: 0.5,
    margin: 0.1,
    expect: "advise",
  });
  assert.deepEqual(command.argv, [
    "-m",
    "evaluation.probe.semantic_probe",
    "--text",
    "da mình mụn viêm nhiều nên dùng gì?",
    "--k",
    "5",
    "--oos",
    "0.5",
    "--margin",
    "0.1",
    "--expect",
    "advise",
    "--neighbors",
    "--json",
  ]);
  assert.equal(COMMAND_IDS.includes("probe_semantic"), true);

  const minimal = buildCommand("probe_semantic", { text: "mụn đầu đen là gì?" });
  assert.deepEqual(minimal.argv, [
    "-m",
    "evaluation.probe.semantic_probe",
    "--text",
    "mụn đầu đen là gì?",
    "--neighbors",
    "--json",
  ]);
});

test("probe_semantic keeps metacharacters inert inside a single argv element", () => {
  // spawn(shell:false) + argv array: ký tự shell được truyền nguyên văn, không nối chuỗi.
  const tricky = 'mụn "đầu đen" $100; rm -rf & | `x`';
  const command = buildCommand("probe_semantic", { text: tricky });
  assert.equal(command.argv[3], tricky);
  assert.equal(command.argv.includes(tricky), true);
});

test("probe_semantic rejects empty, multi-line, over-long text and invalid values", () => {
  for (const text of ["  ", "a\nb", "a\rb", "x".repeat(2001)]) {
    assert.throws(() => buildCommand("probe_semantic", { text }));
  }
  assert.throws(() => buildCommand("probe_semantic", { text: "ok", k: 0 }));
  assert.throws(() => buildCommand("probe_semantic", { text: "ok", k: 101 }));
  assert.throws(() => buildCommand("probe_semantic", { text: "ok", oos: 2.5 }));
  assert.throws(() => buildCommand("probe_semantic", { text: "ok", margin: -0.1 }));
  assert.throws(() =>
    buildCommand("probe_semantic", { text: "ok", expect: "other" }),
  );
});

test("judge command delegates provider and pointwise model to Python settings", () => {
  const command = buildCommand("judge", {
    runDir: "evaluation/reports/main_2x2_t3",
    dataset: "evaluation/datasets/v1/d2_test.jsonl",
  });
  assert.deepEqual(command.argv, [
    "-m",
    "evaluation.judges.run_judge",
    "--run-dir",
    "evaluation/reports/main_2x2_t3",
    "--dataset",
    "evaluation/datasets/v1/d2_test.jsonl",
    "--faithfulness-model",
    "gpt-5-nano-2025-08-07",
    "--workers",
    "4",
  ]);
  assert.equal("judgeProvider" in command.normalizedArgs, false);
  assert.equal("judgeModel" in command.normalizedArgs, false);
  assert.equal(
    command.normalizedArgs.faithfulnessModel,
    "gpt-5-nano-2025-08-07",
  );
  assert.equal(command.normalizedArgs.judgeWorkers, 4);
});

test("unified intake and four bottleneck arms are dashboard commands", () => {
  assert.equal(COMMAND_IDS.includes("intake_unified"), true);
  assert.equal(COMMAND_IDS.includes("bottleneck"), true);
  assert.deepEqual(buildCommand("intake_unified", { limit: 5 }).argv, [
    "scripts/eval_unified_intake.py",
    "--limit",
    "5",
  ]);

  for (const arm of ["z", "x", "y", "w"]) {
    const command = buildCommand("bottleneck", { arm, limit: 5 });
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
    () => buildCommand("bottleneck", { arm: "invalid" }),
    /Arm chỉ nhận z\|x\|y\|w/,
  );
});
