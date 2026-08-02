import assert from "node:assert/strict";
import test from "node:test";
import {
  DATASET_CONFIG,
  DATASET_KEYS,
  migrateDatasetKey,
  validateRetrievalReviewCandidate,
} from "../lib/dataset-review-catalog.ts";

test("dataset review catalog uses descriptive development key", () => {
  assert.equal(DATASET_KEYS[0], "dev_tuning");
  assert.deepEqual(DATASET_CONFIG.dev_tuning, {
    label: "Bộ dev để tinh chỉnh",
    sourceArea: "v1",
    sourceFile: "dev_tuning.jsonl",
    targetFile: "dev_tuning.jsonl",
    description:
      "Dev-only set để chỉnh prompt, threshold và judge rubric; không báo cáo metric.",
  });
});

test("retrieval review validates manual intent and qrels without generation fields", () => {
  assert.deepEqual(DATASET_CONFIG.retrieval, {
    label: "Tìm kiếm tài liệu",
    sourceArea: "drafts",
    sourceFile: "retrieval_test.draft.jsonl",
    targetFile: "retrieval_test.jsonl",
    description:
      "Qrels retrieval hiện có, bổ sung intent_label do người review gán tay cho arm X.",
  });
  const valid = {
    sample_id: "d8-1",
    user_query: "BPO là gì?",
    task_type: "retrieval_qrels",
    intent_label: "knowledge",
    relevant_chunk_ids: ["chunk-1"],
    relevance_grade: { "chunk-1": 2 },
  };
  assert.deepEqual(validateRetrievalReviewCandidate(valid), []);
  assert.match(
    validateRetrievalReviewCandidate({ ...valid, intent_label: null }).join(" "),
    /intent_label/,
  );
  assert.match(
    validateRetrievalReviewCandidate({ ...valid, relevant_chunk_ids: [] }).join(" "),
    /relevant_chunk_ids/,
  );
});

test("legacy review keys migrate without dropping decisions", () => {
  assert.deepEqual(
    ["d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"].map(migrateDatasetKey),
    [...DATASET_KEYS],
  );
  assert.equal(migrateDatasetKey("answer_quality"), "answer_quality");
});
