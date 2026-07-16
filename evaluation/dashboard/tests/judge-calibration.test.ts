import assert from "node:assert/strict";
import test from "node:test";
import { summarizeJudgeCalibration } from "../lib/judge-calibration.ts";

test("missing judge bias artifact is not calibrated", () => {
  assert.deepEqual(summarizeJudgeCalibration(null), {
    available: false,
    calibrated: false,
    failedChecks: ["missing"],
  });
});

test("judge calibration reports failed checks", () => {
  assert.deepEqual(
    summarizeJudgeCalibration({
      position_bias: { pass: true },
      length_bias: { pass: false },
      consistency: { pass: true },
    }),
    {
      available: true,
      calibrated: false,
      failedChecks: ["length_bias"],
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
