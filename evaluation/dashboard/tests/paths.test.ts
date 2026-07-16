import assert from "node:assert/strict";
import test from "node:test";
import {
  EvaluationPathAccessError,
  resolveEvaluationPath,
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
