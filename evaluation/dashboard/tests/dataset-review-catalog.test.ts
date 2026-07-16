import assert from "node:assert/strict";
import test from "node:test";
import {
  DATASET_CONFIG,
  DATASET_KEYS,
} from "../lib/dataset-review-catalog.ts";

test("dataset review catalog includes D1 development seed", () => {
  assert.equal(DATASET_KEYS[0], "d1");
  assert.deepEqual(DATASET_CONFIG.d1, {
    label: "D1 · Development",
    sourceArea: "v1",
    sourceFile: "d1_dev_seed.jsonl",
    targetFile: "d1_dev_seed.jsonl",
    description:
      "Dev-only set để chỉnh prompt, threshold và judge rubric; không báo cáo metric.",
  });
});
