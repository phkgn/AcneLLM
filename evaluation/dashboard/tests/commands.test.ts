import assert from "node:assert/strict";
import test from "node:test";
import { t3OutputFlags } from "../lib/command-flags.ts";

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
