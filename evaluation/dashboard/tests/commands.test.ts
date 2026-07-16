import assert from "node:assert/strict";
import test from "node:test";
import {
  checkGateRunFlags,
  t3OutputFlags,
} from "../lib/command-flags.ts";
import { COMMAND_IDS } from "../lib/command-ids.ts";

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
