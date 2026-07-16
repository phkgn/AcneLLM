export const DATASET_KEYS = [
  "d1",
  "d2",
  "d3",
  "d4",
  "d5",
  "d6",
  "d7",
] as const;

export type DatasetKey = (typeof DATASET_KEYS)[number];

export type DatasetConfig = {
  label: string;
  sourceArea: "v1" | "drafts";
  sourceFile: string;
  targetFile: string;
  description: string;
};

export const DATASET_CONFIG: Record<DatasetKey, DatasetConfig> = {
  d1: {
    label: "D1 · Development",
    sourceArea: "v1",
    sourceFile: "d1_dev_seed.jsonl",
    targetFile: "d1_dev_seed.jsonl",
    description:
      "Dev-only set để chỉnh prompt, threshold và judge rubric; không báo cáo metric.",
  },
  d2: {
    label: "D2 · Main test",
    sourceArea: "drafts",
    sourceFile: "d2_test.draft.jsonl",
    targetFile: "d2_test.jsonl",
    description: "Câu hỏi acne chính: advise, clarify và knowledge.",
  },
  d3: {
    label: "D3 · Challenge",
    sourceArea: "drafts",
    sourceFile: "d3_challenge.draft.jsonl",
    targetFile: "d3_challenge.jsonl",
    description: "Hard cases để phân tích giới hạn; không dùng làm gate.",
  },
  d4: {
    label: "D4 · Safety",
    sourceArea: "drafts",
    sourceFile: "d4_safety.draft.jsonl",
    targetFile: "d4_safety.jsonl",
    description: "Tình huống high/critical risk và hành vi triage an toàn.",
  },
  d5: {
    label: "D5 · Multi-turn",
    sourceArea: "drafts",
    sourceFile: "d5_multiturn.draft.jsonl",
    targetFile: "d5_multiturn.jsonl",
    description: "Câu hỏi cần dùng đúng lịch sử hội thoại.",
  },
  d6: {
    label: "D6 · OOD",
    sourceArea: "drafts",
    sourceFile: "d6_ood.draft.jsonl",
    targetFile: "d6_ood.jsonl",
    description: "Yêu cầu ngoài phạm vi AcneLLM và expected reject.",
  },
  d7: {
    label: "D7 · Adversarial",
    sourceArea: "drafts",
    sourceFile: "d7_adversarial.draft.jsonl",
    targetFile: "d7_adversarial.jsonl",
    description: "Prompt injection, extraction và yêu cầu đối kháng.",
  },
};
