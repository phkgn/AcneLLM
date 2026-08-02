import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import {
  DATASET_CONFIG,
  DATASET_KEYS,
  type DatasetKey,
  migrateDatasetKey,
  validateRetrievalReviewCandidate,
} from "@/lib/dataset-review-catalog";
import { readJsonl } from "@/lib/files";
import {
  DATASET_REVIEWS_BACKUP_FILE,
  DATASET_REVIEWS_FILE,
  EVALUATION_ROOT,
} from "@/lib/paths";

export { DATASET_CONFIG, DATASET_KEYS };
export type { DatasetKey };

export const REVIEW_STATUSES = [
  "pending",
  "approved",
  "needs_edit",
  "rejected",
] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

type JsonRecord = Record<string, unknown>;

const DRAFTS_ROOT = path.join(EVALUATION_ROOT, "datasets", "drafts", "v1");
const VERSIONED_ROOT = path.join(EVALUATION_ROOT, "datasets", "v1");
const EDITABLE_FIELDS = [
  "user_query",
  "task_type",
  "conversation_history",
  "intent_label",
  "subject_label",
  "clinical_risk_level",
  "expected_behavior",
  "expected_answer_points",
  "forbidden_claims",
  "reference_answer",
  "difficulty",
  "scenario_tags",
] as const;

const VALID_RISKS = new Set(["low", "medium", "high", "critical"]);
const VALID_DIFFICULTIES = new Set(["easy", "medium", "hard"]);

export interface ReviewDecision {
  sampleId: string;
  datasetKey: DatasetKey;
  status: Exclude<ReviewStatus, "pending">;
  humanNotes: string;
  editedFields: JsonRecord;
  sourceHash: string;
  reviewedAt: string;
}

interface ReviewStore {
  version: 1;
  updatedAt: string;
  decisions: Record<string, ReviewDecision>;
}

interface DraftEntry {
  datasetKey: DatasetKey;
  sourceFile: string;
  row: JsonRecord;
  sourceHash: string;
}

export interface ReviewItem {
  datasetKey: DatasetKey;
  sourceFile: string;
  targetFile: string;
  row: JsonRecord;
  sourceRow: JsonRecord;
  sourceHash: string;
  status: ReviewStatus;
  stale: boolean;
  edited: boolean;
  decision: ReviewDecision | null;
  validationErrors: string[];
}

export interface ReviewSummary {
  total: number;
  pending: number;
  approved: number;
  needs_edit: number;
  rejected: number;
  stale: number;
  unresolved: number;
  readyToExport: boolean;
}

export class ReviewConflictError extends Error {
  summary: ReviewSummary;

  constructor(message: string, summary: ReviewSummary) {
    super(message);
    this.name = "ReviewConflictError";
    this.summary = summary;
  }
}

let writeQueue: Promise<void> = Promise.resolve();

function emptyStore(): ReviewStore {
  return {
    version: 1,
    updatedAt: new Date(0).toISOString(),
    decisions: {},
  };
}

function hashRow(row: JsonRecord): string {
  return createHash("sha256").update(JSON.stringify(row)).digest("hex");
}

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringOrNull(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function stringList(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${field} phải là mảng.`);
  }
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function normalizeConversationHistory(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) {
    throw new Error("conversation_history phải là mảng.");
  }
  return value.map((message, index) => {
    if (!isRecord(message)) {
      throw new Error(`conversation_history[${index}] phải là object.`);
    }
    const role = String(message.role ?? "").trim();
    const content = String(message.content ?? "").trim();
    if (!["user", "assistant", "system"].includes(role) || !content) {
      throw new Error(
        `conversation_history[${index}] cần role hợp lệ và content không rỗng.`,
      );
    }
    return { role, content };
  });
}

function normalizeEditableField(field: string, value: unknown): unknown {
  if (field === "user_query" || field === "task_type") {
    return String(value ?? "").trim();
  }
  if (
    field === "intent_label" ||
    field === "subject_label" ||
    field === "clinical_risk_level" ||
    field === "expected_behavior" ||
    field === "reference_answer" ||
    field === "difficulty"
  ) {
    return stringOrNull(value);
  }
  if (
    field === "expected_answer_points" ||
    field === "forbidden_claims" ||
    field === "scenario_tags"
  ) {
    return stringList(value, field);
  }
  if (field === "conversation_history") {
    return normalizeConversationHistory(value);
  }
  return value;
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function editedFieldsFromSubmission(
  source: JsonRecord,
  submitted: JsonRecord,
): JsonRecord {
  const edited: JsonRecord = {};
  for (const field of EDITABLE_FIELDS) {
    if (!(field in submitted)) continue;
    const normalized = normalizeEditableField(field, submitted[field]);
    if (!sameValue(source[field], normalized)) {
      edited[field] = normalized;
    }
  }
  return edited;
}

function mergeEditedFields(source: JsonRecord, editedFields: JsonRecord): JsonRecord {
  const merged = { ...source };
  for (const field of EDITABLE_FIELDS) {
    if (field in editedFields) {
      merged[field] = editedFields[field];
    }
  }
  return merged;
}

function validateStringArray(
  row: JsonRecord,
  field: string,
  errors: string[],
  requireItems = false,
) {
  const value = row[field];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    errors.push(`${field} phải là mảng string.`);
  } else if (requireItems && value.length === 0) {
    errors.push(`${field} không được rỗng.`);
  }
}

export function validateReviewCandidate(
  row: JsonRecord,
  datasetKey: DatasetKey,
): string[] {
  const errors: string[] = [];
  if (!String(row.sample_id ?? "").trim()) errors.push("Thiếu sample_id.");
  if (!String(row.user_query ?? "").trim()) errors.push("user_query không được rỗng.");
  if (!String(row.task_type ?? "").trim()) errors.push("task_type không được rỗng.");
  if (datasetKey !== "retrieval") {
    if (!String(row.expected_behavior ?? "").trim()) {
      errors.push("expected_behavior không được rỗng.");
    }
    validateStringArray(row, "expected_answer_points", errors, true);
    validateStringArray(row, "forbidden_claims", errors);
    validateStringArray(row, "scenario_tags", errors);
  }

  const risk = row.clinical_risk_level;
  if (risk !== null && risk !== undefined && !VALID_RISKS.has(String(risk))) {
    errors.push("clinical_risk_level không hợp lệ.");
  }
  const difficulty = row.difficulty;
  if (
    difficulty !== null &&
    difficulty !== undefined &&
    !VALID_DIFFICULTIES.has(String(difficulty))
  ) {
    errors.push("difficulty không hợp lệ.");
  }

  try {
    normalizeConversationHistory(row.conversation_history ?? []);
  } catch (error) {
    errors.push((error as Error).message);
  }

  if (datasetKey === "dev_tuning") {
    if (
      !["advise", "clarify", "knowledge", "safety"].includes(
        String(row.task_type),
      )
    ) {
      errors.push(
        "Bộ dev task_type phải là advise, clarify, knowledge hoặc safety.",
      );
    }
  } else if (datasetKey === "answer_quality") {
    if (!["advise", "clarify", "knowledge"].includes(String(row.task_type))) {
      errors.push("Bộ chất lượng câu trả lời cần task_type advise, clarify hoặc knowledge.");
    }
  } else if (datasetKey === "hard_cases") {
    if (!["advise", "clarify", "knowledge"].includes(String(row.task_type))) {
      errors.push("Bộ ca khó cần task_type advise, clarify hoặc knowledge.");
    }
    if (row.difficulty !== "hard") errors.push("Ca khó cần difficulty=hard.");
    if (
      !Array.isArray(row.expected_answer_points) ||
      row.expected_answer_points.length < 3
    ) {
      errors.push("Ca khó cần ít nhất 3 expected_answer_points.");
    }
    if (!Array.isArray(row.forbidden_claims) || row.forbidden_claims.length < 1) {
      errors.push("Ca khó cần forbidden_claims không rỗng.");
    }
    if (!Array.isArray(row.scenario_tags) || row.scenario_tags.length < 2) {
      errors.push("Ca khó cần ít nhất 2 challenge dimensions trong scenario_tags.");
    }
  } else if (datasetKey === "safety") {
    if (row.task_type !== "safety") errors.push("Bộ an toàn cần task_type=safety.");
    if (!["high", "critical"].includes(String(risk))) {
      errors.push("Bộ an toàn cần clinical_risk_level high hoặc critical.");
    }
  } else if (datasetKey === "multi_turn") {
    if (row.task_type !== "multi_turn") {
      errors.push("Bộ nhiều lượt cần task_type=multi_turn.");
    }
    if (!Array.isArray(row.conversation_history) || row.conversation_history.length === 0) {
      errors.push("Bộ nhiều lượt cần conversation_history không rỗng.");
    }
  } else if (datasetKey === "out_of_scope") {
    if (row.task_type !== "ood") errors.push("Bộ ngoài phạm vi cần task_type=ood.");
    if (row.intent_label !== "reject") errors.push("Bộ ngoài phạm vi cần intent_label=reject.");
  } else if (datasetKey === "adversarial") {
    if (row.task_type !== "adversarial") {
      errors.push("Bộ đối kháng cần task_type=adversarial.");
    }
    if (row.intent_label !== "reject") errors.push("Bộ đối kháng cần intent_label=reject.");
  } else if (datasetKey === "retrieval") {
    errors.push(...validateRetrievalReviewCandidate(row));
  }
  return errors;
}

async function readStore(): Promise<ReviewStore> {
  try {
    const parsed = JSON.parse(
      await fs.readFile(DATASET_REVIEWS_FILE, "utf8"),
    ) as Partial<ReviewStore>;
    if (parsed.version !== 1 || !isRecord(parsed.decisions)) {
      throw new Error("Sai schema review store.");
    }
    const decisions = Object.fromEntries(
      Object.entries(parsed.decisions).map(([sampleId, rawDecision]) => {
        if (!isRecord(rawDecision)) {
          throw new Error(`Quyết định review ${sampleId} không hợp lệ.`);
        }
        const datasetKey = migrateDatasetKey(rawDecision.datasetKey);
        if (!datasetKey) {
          throw new Error(`datasetKey của ${sampleId} không hợp lệ.`);
        }
        return [sampleId, { ...rawDecision, datasetKey } as ReviewDecision];
      }),
    );
    return {
      version: 1,
      updatedAt: String(parsed.updatedAt ?? new Date(0).toISOString()),
      decisions,
    };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return emptyStore();
    throw new Error(
      `Không đọc được ${path.basename(DATASET_REVIEWS_FILE)}: ${(error as Error).message}`,
    );
  }
}

async function writeStore(store: ReviewStore): Promise<void> {
  const temporary = `${DATASET_REVIEWS_FILE}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(store, null, 2)}\n`, "utf8");
  try {
    await fs.copyFile(DATASET_REVIEWS_FILE, DATASET_REVIEWS_BACKUP_FILE);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  try {
    await fs.rename(temporary, DATASET_REVIEWS_FILE);
  } catch {
    await fs.rm(DATASET_REVIEWS_FILE, { force: true });
    await fs.rename(temporary, DATASET_REVIEWS_FILE);
  }
}

async function loadDraftCorpus(): Promise<DraftEntry[]> {
  const groups = await Promise.all(
    DATASET_KEYS.map(async (datasetKey) => {
      const config = DATASET_CONFIG[datasetKey];
      const sourceRoot =
        config.sourceArea === "v1" ? VERSIONED_ROOT : DRAFTS_ROOT;
      const sourcePath = path.join(sourceRoot, config.sourceFile);
      const rows = await readJsonl(sourcePath);
      return rows.map((row) => ({
        datasetKey,
        sourceFile: config.sourceFile,
        row,
        sourceHash: hashRow(row),
      }));
    }),
  );
  const corpus = groups.flat();
  const seen = new Set<string>();
  for (const entry of corpus) {
    const sampleId = String(entry.row.sample_id ?? "");
    if (!sampleId) {
      throw new Error(`${entry.sourceFile} có sample thiếu sample_id.`);
    }
    if (seen.has(sampleId)) {
      throw new Error(`sample_id trùng giữa các draft: ${sampleId}`);
    }
    seen.add(sampleId);
  }
  return corpus;
}

function buildItem(
  entry: DraftEntry,
  decision: ReviewDecision | undefined,
): ReviewItem {
  const stale = Boolean(decision && decision.sourceHash !== entry.sourceHash);
  const row = decision
    ? mergeEditedFields(entry.row, decision.editedFields)
    : entry.row;
  return {
    datasetKey: entry.datasetKey,
    sourceFile: entry.sourceFile,
    targetFile: DATASET_CONFIG[entry.datasetKey].targetFile,
    row,
    sourceRow: entry.row,
    sourceHash: entry.sourceHash,
    status: decision?.status ?? "pending",
    stale,
    edited: Boolean(decision && Object.keys(decision.editedFields).length),
    decision: decision ?? null,
    validationErrors: validateReviewCandidate(row, entry.datasetKey),
  };
}

export async function loadReviewItems(): Promise<ReviewItem[]> {
  const [corpus, store] = await Promise.all([loadDraftCorpus(), readStore()]);
  return corpus.map((entry) => buildItem(entry, store.decisions[String(entry.row.sample_id)]));
}

export function summarizeReview(items: ReviewItem[]): ReviewSummary {
  const summary: ReviewSummary = {
    total: items.length,
    pending: 0,
    approved: 0,
    needs_edit: 0,
    rejected: 0,
    stale: 0,
    unresolved: 0,
    readyToExport: false,
  };
  for (const item of items) {
    if (item.stale) {
      summary.stale += 1;
      continue;
    }
    summary[item.status] += 1;
  }
  summary.unresolved =
    summary.pending + summary.needs_edit + summary.stale;
  summary.readyToExport =
    summary.total > 0 && summary.unresolved === 0 && summary.approved > 0;
  return summary;
}

export async function saveReviewDecision(input: {
  sampleId: string;
  status: ReviewStatus;
  humanNotes?: string;
  editedFields?: JsonRecord;
}): Promise<ReviewItem> {
  let savedItem: ReviewItem | null = null;
  const operation = writeQueue.then(async () => {
    const corpus = await loadDraftCorpus();
    const entry = corpus.find(
      (candidate) => String(candidate.row.sample_id) === input.sampleId,
    );
    if (!entry) throw new Error(`Không tìm thấy sample_id ${input.sampleId}.`);

    const store = await readStore();
    if (input.status === "pending") {
      delete store.decisions[input.sampleId];
    } else {
      const editedFields = editedFieldsFromSubmission(
        entry.row,
        input.editedFields ?? {},
      );
      const candidate = mergeEditedFields(entry.row, editedFields);
      const validationErrors = validateReviewCandidate(
        candidate,
        entry.datasetKey,
      );
      if (input.status === "approved" && validationErrors.length) {
        throw new Error(
          `Không thể approve vì còn lỗi: ${validationErrors.join(" ")}`,
        );
      }
      store.decisions[input.sampleId] = {
        sampleId: input.sampleId,
        datasetKey: entry.datasetKey,
        status: input.status,
        humanNotes: String(input.humanNotes ?? "").trim(),
        editedFields,
        sourceHash: entry.sourceHash,
        reviewedAt: new Date().toISOString(),
      };
    }
    store.updatedAt = new Date().toISOString();
    await writeStore(store);
    savedItem = buildItem(entry, store.decisions[input.sampleId]);
  });
  writeQueue = operation.then(
    () => undefined,
    () => undefined,
  );
  await operation;
  if (!savedItem) throw new Error("Không lưu được quyết định review.");
  return savedItem;
}

export async function exportApprovedDataset(
  datasetKey: DatasetKey,
  datasetVersion = "v1.0",
): Promise<{ filename: string; rows: JsonRecord[]; summary: ReviewSummary }> {
  const items = (await loadReviewItems()).filter(
    (item) => item.datasetKey === datasetKey,
  );
  const summary = summarizeReview(items);
  if (!summary.readyToExport) {
    throw new ReviewConflictError(
      `Dataset còn ${summary.unresolved} mẫu chưa xử lý xong.`,
      summary,
    );
  }
  const rows = items
    .filter((item) => !item.stale && item.status === "approved")
    .map(
      (item): JsonRecord => ({
        ...item.row,
        dataset_version: datasetVersion,
        annotation_status: "approved",
        human_notes:
          item.decision?.humanNotes ||
          "Human reviewed: labels and expected behavior verified.",
      }),
    );
  for (const row of rows) {
    const errors = validateReviewCandidate(row, datasetKey);
    if (errors.length) {
      throw new Error(
        `${String(row.sample_id)} không hợp lệ khi export: ${errors.join(" ")}`,
      );
    }
  }
  return {
    filename: DATASET_CONFIG[datasetKey].targetFile,
    rows,
    summary,
  };
}
