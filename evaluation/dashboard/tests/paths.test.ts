import assert from "node:assert/strict";
import test from "node:test";
import {
  EvaluationPathAccessError,
  resolveEvaluationPath,
  resolveWhitelistedRepoVisual,
} from "../lib/paths.ts";

test("path traversal is classified as forbidden access", () => {
  assert.throws(
    () => resolveEvaluationPath("../../.env"),
    EvaluationPathAccessError,
  );
});

test("valid evaluation paths remain resolvable", () => {
  assert.match(
    resolveEvaluationPath("evaluation/reports/gate_check.json"),
    /evaluation[\\/]reports[\\/]gate_check\.json$/,
  );
});

test("only the two repository HTML visuals are externally whitelisted", async () => {
  assert.match(
    (await resolveWhitelistedRepoVisual("acnellm_pipeline.html")) ?? "",
    /acnellm_pipeline\.html$/,
  );
  assert.match(
    (await resolveWhitelistedRepoVisual("pipeline_simulator.html")) ?? "",
    /pipeline_simulator\.html$/,
  );
  assert.equal(await resolveWhitelistedRepoVisual("../.env"), null);
});
