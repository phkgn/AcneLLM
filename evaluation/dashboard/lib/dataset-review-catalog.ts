export const DATASET_KEYS = [
  "dev_tuning",
  "answer_quality",
  "hard_cases",
  "safety",
  "multi_turn",
  "out_of_scope",
  "adversarial",
  "retrieval",
] as const;

export type DatasetKey = (typeof DATASET_KEYS)[number];

const LEGACY_DATASET_KEYS: Record<string, DatasetKey> = {
  d1: "dev_tuning",
  d2: "answer_quality",
  d3: "hard_cases",
  d4: "safety",
  d5: "multi_turn",
  d6: "out_of_scope",
  d7: "adversarial",
  d8: "retrieval",
};

export function migrateDatasetKey(value: unknown): DatasetKey | null {
  const key = String(value ?? "");
  if (DATASET_KEYS.includes(key as DatasetKey)) return key as DatasetKey;
  return LEGACY_DATASET_KEYS[key] ?? null;
}

export type DatasetConfig = {
  label: string;
  sourceArea: "v1" | "drafts";
  sourceFile: string;
  targetFile: string;
  description: string;
};

export function validateRetrievalReviewCandidate(
  row: Record<string, unknown>,
): string[] {
  const errors: string[] = [];
  if (!new Set(["advise", "knowledge", "clarify", "reject"]).has(String(row.intent_label))) {
    errors.push("Retrieval intent_label phải là advise, knowledge, clarify hoặc reject.");
  }
  const chunkIds = row.relevant_chunk_ids;
  if (
    !Array.isArray(chunkIds) ||
    chunkIds.length === 0 ||
    chunkIds.some((item) => typeof item !== "string" || !item.trim())
  ) {
    errors.push("relevant_chunk_ids phải là mảng string không rỗng.");
  }
  const grades = row.relevance_grade;
  if (
    !grades ||
    typeof grades !== "object" ||
    Array.isArray(grades) ||
    Object.keys(grades).length === 0 ||
    Object.entries(grades).some(
      ([chunkId, grade]) =>
        !chunkId.trim() ||
        typeof grade !== "number" ||
        !Number.isInteger(grade) ||
        grade < 0,
    )
  ) {
    errors.push("Retrieval relevance_grade phải là map chunk_id -> số nguyên không âm.");
  }
  return errors;
}

export const DATASET_CONFIG: Record<DatasetKey, DatasetConfig> = {
  dev_tuning: {
    label: "Bộ dev để tinh chỉnh",
    sourceArea: "v1",
    sourceFile: "dev_tuning.jsonl",
    targetFile: "dev_tuning.jsonl",
    description:
      "Dev-only set để chỉnh prompt, threshold và judge rubric; không báo cáo metric.",
  },
  answer_quality: {
    label: "Chất lượng câu trả lời",
    sourceArea: "drafts",
    sourceFile: "answer_quality_test.draft.jsonl",
    targetFile: "answer_quality_test.jsonl",
    description: "Câu hỏi acne chính: advise, clarify và knowledge.",
  },
  hard_cases: {
    label: "Ca khó",
    sourceArea: "drafts",
    sourceFile: "hard_cases_test.draft.jsonl",
    targetFile: "hard_cases_test.jsonl",
    description: "Hard cases để phân tích giới hạn; không dùng làm gate.",
  },
  safety: {
    label: "An toàn",
    sourceArea: "drafts",
    sourceFile: "safety_test.draft.jsonl",
    targetFile: "safety_test.jsonl",
    description: "Tình huống high/critical risk và hành vi triage an toàn.",
  },
  multi_turn: {
    label: "Hội thoại nhiều lượt",
    sourceArea: "drafts",
    sourceFile: "multi_turn_test.draft.jsonl",
    targetFile: "multi_turn_test.jsonl",
    description: "Câu hỏi cần dùng đúng lịch sử hội thoại.",
  },
  out_of_scope: {
    label: "Ngoài phạm vi",
    sourceArea: "drafts",
    sourceFile: "out_of_scope_test.draft.jsonl",
    targetFile: "out_of_scope_test.jsonl",
    description: "Yêu cầu ngoài phạm vi AcneLLM và expected reject.",
  },
  adversarial: {
    label: "Đối kháng",
    sourceArea: "drafts",
    sourceFile: "adversarial_test.draft.jsonl",
    targetFile: "adversarial_test.jsonl",
    description: "Prompt injection, extraction và yêu cầu đối kháng.",
  },
  retrieval: {
    label: "Tìm kiếm tài liệu",
    sourceArea: "drafts",
    sourceFile: "retrieval_test.draft.jsonl",
    targetFile: "retrieval_test.jsonl",
    description:
      "Qrels retrieval hiện có, bổ sung intent_label do người review gán tay cho arm X.",
  },
};
