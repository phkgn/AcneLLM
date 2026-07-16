import assert from "node:assert/strict";
import test from "node:test";
import { normalizeGateArtifact } from "../lib/gates.ts";

test("gate badges normalize only the harness gate artifact", () => {
  const normalized = normalizeGateArtifact({
    n_pass: 1,
    n_total: 3,
    checks: [
      {
        name: "generation.parse_success_rate",
        actual: 1,
        threshold: 0.98,
        pass: true,
      },
      {
        name: "generation.citation_valid_rate",
        actual: null,
        threshold: 0.95,
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
        metric: "parse_success_rate",
        value: 1,
        status: "pass",
      },
      {
        section: "generation",
        metric: "citation_valid_rate",
        value: null,
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
