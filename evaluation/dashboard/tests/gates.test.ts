import assert from "node:assert/strict";
import test from "node:test";
import { normalizeGateArtifact } from "../lib/gates.ts";

test("gate badges normalize only the harness gate artifact", () => {
  const normalized = normalizeGateArtifact({
    n_pass: 1,
    n_total: 3,
    checks: [
      {
        name: "generation.grounded_sentence_rate",
        actual: 0.6,
        threshold: 0.5,
        pass: true,
      },
      {
        name: "safety.known_pattern_violations",
        actual: 1,
        threshold: 0,
        pass: false,
      },
      {
        name: "validation.dataset_validity",
        actual: 0,
        threshold: 1,
        pass: false,
      },
    ],
  });

  assert.deepEqual(normalized.summary, {
    pass: 1,
    fail: 2,
    missing: 0,
  });
  assert.deepEqual(
    normalized.checks.map((check) => ({
      section: check.section,
      metric: check.metric,
      value: check.value,
      status: check.status,
    })),
    [
      {
        section: "generation",
        metric: "grounded_sentence_rate",
        value: 0.6,
        status: "pass",
      },
      {
        section: "safety",
        metric: "known_pattern_violations",
        value: 1,
        status: "fail",
      },
      {
        section: "validation",
        metric: "dataset_validity",
        value: 0,
        status: "fail",
      },
    ],
  );
});
