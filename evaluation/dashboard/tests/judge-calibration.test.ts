import assert from "node:assert/strict";
import test from "node:test";
import { summarizeJudgeCalibration } from "../lib/judge-calibration.ts";

test("missing judge bias artifact is not calibrated", () => {
  assert.deepEqual(summarizeJudgeCalibration(null), {
    available: false,
    calibrated: false,
    failedChecks: ["missing"],
    provider: null,
    model: null,
  });
});

test("judge calibration reports failed checks", () => {
  assert.deepEqual(
    summarizeJudgeCalibration({
      position_bias: { pass: true },
      length_bias: { pass: false },
      consistency: { pass: true },
      judge_provider: "openai",
      judge_model: "gpt-5.4-mini",
    }),
    {
      available: true,
      calibrated: false,
      failedChecks: ["length_bias"],
      provider: "openai",
      model: "gpt-5.4-mini",
    },
  );
});

test("judge calibration passes only when every recorded check passes", () => {
  assert.equal(
    summarizeJudgeCalibration({
      position_bias: { pass: true },
      length_bias: { pass: true },
      consistency: { pass: true },
    }).calibrated,
    true,
  );
});
