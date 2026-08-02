import assert from "node:assert/strict";
import test from "node:test";
import {
  parseRunAllSummary,
  runAllStepPosition,
} from "../lib/run-all.ts";

test("parseRunAllSummary accepts the machine-readable seven-step schema", () => {
  const statuses = ["ok", "ok", "ok", "running", "pending", "pending", "pending"];
  const ids = [
    "preflight",
    "intake_eval",
    "rag_eval",
    "answer_generation",
    "scoring_report",
    "bottleneck",
    "figures",
  ];
  const summary = parseRunAllSummary({
    run_id: "thesis_20260726_test",
    out_dir: "evaluation/reports/thesis_20260726_test",
    started_at: "2026-07-26T00:00:00+00:00",
    finished_at: null,
    current_step: "answer_generation",
    steps: ids.map((id, index) => ({
      id,
      label: id,
      status: statuses[index],
      started_at: index <= 3 ? "2026-07-26T00:00:00+00:00" : null,
      finished_at: index < 3 ? "2026-07-26T00:00:01+00:00" : null,
      duration_s: index < 3 ? 1 : null,
      detail: "",
    })),
  });

  assert.ok(summary);
  assert.equal(summary.steps.length, 7);
  assert.equal(runAllStepPosition(summary), 4);
  assert.equal(
    parseRunAllSummary({ ...summary, current_step: "unknown_step" }),
    null,
  );
});
