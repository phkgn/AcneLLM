"use client";

import {
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  Download,
  FileCheck2,
  FilePenLine,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DATASET_CONFIG,
  DATASET_KEYS,
  type DatasetKey,
} from "@/lib/dataset-review-catalog";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
  inputClass,
} from "./ui";

type JsonRecord = Record<string, unknown>;
type DatasetFilter = DatasetKey | "all";
type ReviewStatus = "pending" | "approved" | "needs_edit" | "rejected";
type StatusFilter = ReviewStatus | "stale" | "all";
type KindFilter = "all" | "original" | "variant";

type ReviewSummary = {
  total: number;
  pending: number;
  approved: number;
  needs_edit: number;
  rejected: number;
  stale: number;
  unresolved: number;
  readyToExport: boolean;
};

type DatasetSummary = ReviewSummary & {
  label: string;
  sourceFile: string;
  targetFile: string;
  description: string;
};

type ListItem = {
  sampleId: string;
  datasetKey: DatasetKey;
  sourceFile: string;
  query: string;
  taskType: string;
  intentLabel: unknown;
  riskLevel: unknown;
  difficulty: unknown;
  parentSampleId: string | null;
  isVariant: boolean;
  status: ReviewStatus;
  stale: boolean;
  edited: boolean;
  reviewedAt: string | null;
  validationErrorCount: number;
};

type ListResponse = {
  summary: ReviewSummary;
  byDataset: Record<DatasetKey, DatasetSummary>;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  rows: ListItem[];
};

type ReviewDecision = {
  status: Exclude<ReviewStatus, "pending">;
  humanNotes: string;
  reviewedAt: string;
};

type ParentDetail = ListItem & { row: JsonRecord };

type DetailResponse = ListItem & {
  targetFile: string;
  row: JsonRecord;
  sourceRow: JsonRecord;
  sourceHash: string;
  decision: ReviewDecision | null;
  validationErrors: string[];
  parent: ParentDetail | null;
};

type ReviewForm = {
  userQuery: string;
  taskType: string;
  intentLabel: string;
  subjectLabel: string;
  riskLevel: string;
  difficulty: string;
  expectedBehavior: string;
  expectedAnswerPoints: string;
  forbiddenClaims: string;
  scenarioTags: string;
  conversationHistory: string;
  referenceAnswer: string;
  humanNotes: string;
};

const DATASET_OPTIONS: Array<{
  value: DatasetFilter;
  label: string;
}> = [
  { value: "all", label: "Tất cả D1–D7" },
  ...DATASET_KEYS.map((value) => ({
    value,
    label: DATASET_CONFIG[value].label,
  })),
];

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "Mọi trạng thái" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "needs_edit", label: "Needs edit" },
  { value: "rejected", label: "Rejected" },
  { value: "stale", label: "Stale" },
];

const REVIEW_GUIDES: Record<DatasetKey, string[]> = {
  d1: [
    "D1 chỉ dùng để tune prompt, threshold và judge rubric; không báo cáo metric từ split này.",
    "Thay task_type=unlabeled bằng advise, clarify, knowledge hoặc safety và bổ sung gold expectations.",
    "D1 hiện có các câu trùng lặp; reject hoặc viết lại bản dư, không approve cả hai bản giống hệt.",
  ],
  d2: [
    "Câu hỏi tự nhiên, đúng phạm vi acne và không quá giống template.",
    "Intent/task/risk đúng; expected answer đủ ý nhưng không biến thành đáp án học thuộc.",
    "Typo variant phải giữ nguyên ý nghĩa, intent và mức risk của parent.",
  ],
  d3: [
    "Mẫu phải khó vì có ít nhất hai challenge dimensions, không chỉ vì câu dài.",
    "Nhận diện đúng phần bất định, mâu thuẫn hoặc giả định sai cần làm rõ.",
    "Không biến thành safety-critical, multi-turn, OOD hay prompt injection.",
  ],
  d4: [
    "Risk phải high/critical và escalation tương xứng với dấu hiệu người dùng nêu.",
    "Không chẩn đoán chắc chắn, không kê liều/ngừng thuốc nguy hiểm.",
    "Forbidden claims phải chặn reassurance quá mức và hướng dẫn có thể gây hại.",
  ],
  d5: [
    "History nhất quán và câu hiện tại thực sự cần dữ kiện từ lượt trước.",
    "Expected behavior chỉ dùng thông tin đã xuất hiện, không bịa sản phẩm/triệu chứng.",
    "Kiểm tra đại từ tham chiếu, thay đổi routine và timeline.",
  ],
  d6: [
    "Yêu cầu thật sự ngoài phạm vi AcneLLM, không phải câu acne diễn đạt lạ.",
    "Expected behavior từ chối ngắn gọn và chuyển hướng phù hợp.",
    "Không trả lời chuyên sâu lĩnh vực tài chính/pháp lý/kỹ thuật ngoài scope.",
  ],
  d7: [
    "Có hành vi injection/exfiltration hoặc cố ép bỏ qua chỉ dẫn.",
    "Expected behavior từ chối phần độc hại nhưng vẫn giúp phần yêu cầu an toàn nếu có.",
    "Không lộ system prompt, secret, key, file nội bộ hoặc chain-of-thought.",
  ],
};

const EMPTY_SUMMARY: ReviewSummary = {
  total: 0,
  pending: 0,
  approved: 0,
  needs_edit: 0,
  rejected: 0,
  stale: 0,
  unresolved: 0,
  readyToExport: false,
};

function stringValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function linesValue(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join("\n") : "";
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formFromDetail(detail: DetailResponse): ReviewForm {
  return {
    userQuery: stringValue(detail.row.user_query),
    taskType: stringValue(detail.row.task_type),
    intentLabel: stringValue(detail.row.intent_label),
    subjectLabel: stringValue(detail.row.subject_label),
    riskLevel: stringValue(detail.row.clinical_risk_level),
    difficulty: stringValue(detail.row.difficulty),
    expectedBehavior: stringValue(detail.row.expected_behavior),
    expectedAnswerPoints: linesValue(detail.row.expected_answer_points),
    forbiddenClaims: linesValue(detail.row.forbidden_claims),
    scenarioTags: linesValue(detail.row.scenario_tags),
    conversationHistory: pretty(detail.row.conversation_history ?? []),
    referenceAnswer: stringValue(detail.row.reference_answer),
    humanNotes: detail.decision?.humanNotes ?? "",
  };
}

function statusLabel(item: Pick<ListItem, "status" | "stale">): string {
  if (item.stale) return "Stale";
  return {
    pending: "Pending",
    approved: "Approved",
    needs_edit: "Needs edit",
    rejected: "Rejected",
  }[item.status];
}

function statusTone(
  item: Pick<ListItem, "status" | "stale">,
): "good" | "bad" | "warn" | "neutral" {
  if (item.stale) return "warn";
  if (item.status === "approved") return "good";
  if (item.status === "rejected") return "bad";
  if (item.status === "needs_edit") return "warn";
  return "neutral";
}

export function DatasetReviewClient() {
  const [dataset, setDataset] = useState<DatasetFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [kind, setKind] = useState<KindFilter>("all");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [list, setList] = useState<ListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailResponse | null>(null);
  const [form, setForm] = useState<ReviewForm | null>(null);
  const [dirty, setDirty] = useState(false);
  const [autoNext, setAutoNext] = useState(true);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(queryInput);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [queryInput]);

  const loadList = useCallback(
    async (preferredId?: string | null) => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({
          dataset,
          status,
          kind,
          query,
          page: String(page),
          pageSize: "50",
        });
        const response = await fetch(`/api/datasets/review?${params}`, {
          cache: "no-store",
        });
        const body = (await response.json()) as ListResponse & { error?: string };
        if (!response.ok) {
          throw new Error(body.error ?? "Không thể đọc dataset drafts.");
        }
        setList(body);
        if (body.page !== page) setPage(body.page);
        setSelectedId((current) => {
          const preferred = preferredId ?? current;
          if (preferred && body.rows.some((row) => row.sampleId === preferred)) {
            return preferred;
          }
          return body.rows[0]?.sampleId ?? null;
        });
      } catch (loadError) {
        setError((loadError as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [dataset, kind, page, query, status],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setForm(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setError("");
    void fetch(
      `/api/datasets/review?sampleId=${encodeURIComponent(selectedId)}`,
      {
        cache: "no-store",
        signal: controller.signal,
      },
    )
      .then(async (response) => {
        const body = (await response.json()) as DetailResponse & {
          error?: string;
        };
        if (!response.ok) {
          throw new Error(body.error ?? "Không thể đọc sample.");
        }
        setDetail(body);
        setForm(formFromDetail(body));
        setDirty(false);
      })
      .catch((loadError: Error) => {
        if (loadError.name !== "AbortError") setError(loadError.message);
      })
      .finally(() => setDetailLoading(false));
    return () => controller.abort();
  }, [selectedId]);

  const currentSummary = useMemo(() => {
    if (!list) return EMPTY_SUMMARY;
    return dataset === "all" ? list.summary : list.byDataset[dataset];
  }, [dataset, list]);
  const classifiedCount =
    currentSummary.approved +
    currentSummary.needs_edit +
    currentSummary.rejected;
  const classifiedPercent = currentSummary.total
    ? Math.round((classifiedCount / currentSummary.total) * 100)
    : 0;

  const updateForm = <Key extends keyof ReviewForm>(
    key: Key,
    value: ReviewForm[Key],
  ) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setDirty(true);
    setNotice("");
  };

  const chooseSample = (sampleId: string) => {
    if (
      dirty &&
      sampleId !== selectedId &&
      !window.confirm("Bạn có edit chưa lưu. Bỏ thay đổi và chuyển sample?")
    ) {
      return;
    }
    setSelectedId(sampleId);
  };

  const saveDecision = useCallback(
    async (nextStatus: ReviewStatus) => {
      if (!detail || !form || saving) return;
      setSaving(true);
      setError("");
      setNotice("");
      try {
        let conversationHistory: unknown;
        try {
          conversationHistory = JSON.parse(form.conversationHistory || "[]");
        } catch {
          throw new Error("conversation_history không phải JSON hợp lệ.");
        }
        const editedFields: JsonRecord = {
          user_query: form.userQuery,
          task_type: form.taskType,
          intent_label: form.intentLabel || null,
          subject_label: form.subjectLabel || null,
          clinical_risk_level: form.riskLevel || null,
          difficulty: form.difficulty || null,
          expected_behavior: form.expectedBehavior || null,
          expected_answer_points: splitLines(form.expectedAnswerPoints),
          forbidden_claims: splitLines(form.forbiddenClaims),
          scenario_tags: splitLines(form.scenarioTags),
          conversation_history: conversationHistory,
          reference_answer: form.referenceAnswer || null,
        };
        const response = await fetch("/api/datasets/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sampleId: detail.sampleId,
            status: nextStatus,
            humanNotes: form.humanNotes,
            editedFields,
          }),
        });
        const body = (await response.json()) as DetailResponse & {
          error?: string;
        };
        if (!response.ok) throw new Error(body.error ?? "Không lưu được review.");

        const rows = list?.rows ?? [];
        const index = rows.findIndex((row) => row.sampleId === detail.sampleId);
        const nextId =
          rows[index + 1]?.sampleId ?? rows[index - 1]?.sampleId ?? null;
        setDirty(false);
        setNotice(
          nextStatus === "pending"
            ? `${detail.sampleId}: đã reset về pending.`
            : `${detail.sampleId}: ${statusLabel({
                status: nextStatus,
                stale: false,
              })}.`,
        );
        await loadList(autoNext ? nextId : detail.sampleId);
      } catch (saveError) {
        setError((saveError as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [autoNext, detail, form, list?.rows, loadList, saving],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
      ) {
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey || saving) return;
      const key = event.key.toLowerCase();
      if (key === "a") void saveDecision("approved");
      if (key === "e") void saveDecision("needs_edit");
      if (key === "r") void saveDecision("rejected");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [saveDecision, saving]);

  const canExport =
    dataset !== "all" && currentSummary.readyToExport && !loading;
  const exportUrl =
    dataset === "all"
      ? "#"
      : `/api/datasets/review/export?dataset=${dataset}&version=v1.0`;

  return (
    <>
      <PageHeader
        eyebrow="Human dataset review"
        title="Review và duyệt dataset D1–D7"
        description="Nguồn seed/draft luôn read-only. Approve, edit và reject được lưu thành overlay có source hash; review cũ tự chuyển stale nếu nguồn bị thay đổi."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => void loadList(selectedId)}>
              <RefreshCw size={16} />
              Refresh
            </Button>
            {canExport ? (
              <a
                href={exportUrl}
                className="inline-flex items-center justify-center gap-2 rounded-[10px] bg-clay px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#e18769]"
              >
                <Download size={16} />
                Export {dataset.toUpperCase()}
              </a>
            ) : (
              <button
                disabled
                title={
                  dataset === "all"
                    ? "Chọn một dataset để export."
                    : `Còn ${currentSummary.unresolved} mẫu chưa xử lý.`
                }
                className="inline-flex cursor-not-allowed items-center justify-center gap-2 rounded-[10px] bg-clay px-4 py-2.5 text-sm font-semibold text-white opacity-35"
              >
                <Download size={16} />
                Export
              </button>
            )}
          </div>
        }
      />

      {error ? (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-ember/20 bg-[#321e1a] px-4 py-3 text-sm font-medium text-ember">
          <TriangleAlert className="mt-0.5 shrink-0" size={16} />
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-moss/20 bg-[#1e2b22] px-4 py-3 text-sm font-medium text-moss">
          <CheckCircle2 className="mt-0.5 shrink-0" size={16} />
          {notice}
        </div>
      ) : null}

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <SummaryCard
          label="Total"
          value={currentSummary.total}
          icon={<FileCheck2 size={17} />}
        />
        <SummaryCard
          label="Pending"
          value={currentSummary.pending}
          tone="neutral"
          icon={<CircleDashed size={17} />}
        />
        <SummaryCard
          label="Approved"
          value={currentSummary.approved}
          tone="good"
          icon={<CheckCircle2 size={17} />}
        />
        <SummaryCard
          label="Needs edit"
          value={currentSummary.needs_edit}
          tone="warn"
          icon={<FilePenLine size={17} />}
        />
        <SummaryCard
          label="Rejected"
          value={currentSummary.rejected}
          tone="bad"
          icon={<XCircle size={17} />}
        />
        <SummaryCard
          label="Stale"
          value={currentSummary.stale}
          tone="warn"
          icon={<RefreshCw size={17} />}
        />
      </div>

      <Card className="mb-5 px-5 py-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Tiến độ phân loại</p>
            <p className="mt-1 text-xs text-muted">
              Approved, needs edit hoặc rejected · stale không được tính
            </p>
          </div>
          <p className="font-display text-2xl text-ink">
            {classifiedCount}
            <span className="ml-1 text-base text-muted">
              / {currentSummary.total} · {classifiedPercent}%
            </span>
          </p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-sand">
          <div
            className="h-full rounded-full bg-clay transition-[width] duration-500"
            style={{ width: `${classifiedPercent}%` }}
          />
        </div>
      </Card>

      <Card className="mb-5 p-5">
        <div className="grid gap-3 lg:grid-cols-[1fr_180px_170px_1.35fr_auto]">
          <FilterLabel label="Dataset">
            <select
              value={dataset}
              onChange={(event) => {
                if (dirty && !window.confirm("Bỏ edit chưa lưu và đổi dataset?")) {
                  return;
                }
                setDataset(event.target.value as DatasetFilter);
                setPage(1);
                setSelectedId(null);
              }}
              className={inputClass}
            >
              {DATASET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FilterLabel>
          <FilterLabel label="Status">
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as StatusFilter);
                setPage(1);
                setSelectedId(null);
              }}
              className={inputClass}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FilterLabel>
          <FilterLabel label="Loại mẫu">
            <select
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as KindFilter);
                setPage(1);
                setSelectedId(null);
              }}
              className={inputClass}
            >
              <option value="all">Original + typo</option>
              <option value="original">Original</option>
              <option value="variant">Typo variant</option>
            </select>
          </FilterLabel>
          <FilterLabel label="Search">
            <span className="relative block">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35"
              />
              <input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="sample_id, query, expected behavior…"
                className={`${inputClass} pl-9`}
              />
            </span>
          </FilterLabel>
          <label className="flex items-center gap-2 self-end rounded-[10px] border border-line bg-[#211f1b] px-3 py-2.5 text-sm font-medium text-ink">
            <input
              type="checkbox"
              checked={autoNext}
              onChange={(event) => setAutoNext(event.target.checked)}
              className="h-4 w-4 accent-[#c15f3c]"
            />
            Auto-next
          </label>
        </div>
        {dataset !== "all" && list?.byDataset[dataset] ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4 text-xs text-muted">
            <span>{list.byDataset[dataset].description}</span>
            <span className="font-medium text-ink/70">
              Output: {list.byDataset[dataset].targetFile}
            </span>
          </div>
        ) : null}
      </Card>

      <div className="grid gap-5 xl:grid-cols-[430px_minmax(0,1fr)]">
        <Card className="overflow-hidden xl:sticky xl:top-6 xl:self-start">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <h2 className="font-display text-xl">Review queue</h2>
              <p className="mt-1 text-xs text-muted">
                {list?.total ?? 0} mẫu khớp bộ lọc
              </p>
            </div>
            <Pill tone="neutral">50 / page</Pill>
          </div>
          <div className="max-h-[760px] divide-y divide-line overflow-y-auto xl:max-h-[calc(100vh-230px)]">
            {list?.rows.map((row) => (
              <button
                key={row.sampleId}
                onClick={() => chooseSample(row.sampleId)}
                className={`w-full border-l-[3px] px-5 py-4 text-left transition hover:bg-sand/45 ${
                  selectedId === row.sampleId ? "bg-lime/55" : ""
                } ${
                  row.stale
                    ? "border-l-amber-500"
                    : row.status === "approved"
                      ? "border-l-moss"
                      : row.status === "rejected"
                        ? "border-l-ember"
                        : row.status === "needs_edit"
                          ? "border-l-amber-500"
                          : selectedId === row.sampleId
                            ? "border-l-clay"
                            : "border-l-transparent"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">{row.sampleId}</span>
                      <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-clay">
                        {row.datasetKey}
                      </span>
                      {row.isVariant ? (
                        <span className="text-[10px] font-semibold text-[#83b8cf]">
                          TYPO
                        </span>
                      ) : null}
                      {row.edited ? (
                        <span className="text-[10px] font-semibold text-[#e8b96d]">
                          EDITED
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 line-clamp-3 text-[13px] leading-[1.55] text-ink/72">
                      {row.query || "(query rỗng)"}
                    </p>
                  </div>
                  <Pill tone={statusTone(row)}>{statusLabel(row)}</Pill>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-medium text-muted">
                  <span>{row.taskType}</span>
                  {row.riskLevel ? <span>risk: {String(row.riskLevel)}</span> : null}
                  {row.validationErrorCount ? (
                    <span className="text-ember">
                      {row.validationErrorCount} schema issue
                    </span>
                  ) : null}
                </div>
              </button>
            ))}
            {!list?.rows.length ? (
              <div className="p-5">
                <EmptyState
                  title={loading ? "Đang đọc drafts…" : "Queue trống"}
                  description="Không có sample khớp filter hiện tại. Đổi status hoặc dataset để xem nhóm khác."
                />
              </div>
            ) : null}
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3">
            <button
              disabled={!list || list.page <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-[#211f1b] text-muted transition hover:text-ink disabled:opacity-30"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs font-medium text-muted">
              Page {list?.page ?? 1} / {list?.totalPages ?? 1}
            </span>
            <button
              disabled={!list || list.page >= list.totalPages}
              onClick={() => setPage((value) => value + 1)}
              className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-[#211f1b] text-muted transition hover:text-ink disabled:opacity-30"
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </Card>

        <div className="min-w-0 space-y-5">
          {detail && form ? (
            <>
              <Card className="p-5 sm:p-7">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Pill tone={statusTone(detail)}>
                        {statusLabel(detail)}
                      </Pill>
                      <Pill tone="info">{detail.datasetKey.toUpperCase()}</Pill>
                      <Pill tone={detail.isVariant ? "info" : "neutral"}>
                        {detail.isVariant ? "Typo variant" : "Original"}
                      </Pill>
                      {detail.row.contamination_status === "clean" ? (
                        <Pill tone="good">Contamination clean</Pill>
                      ) : (
                        <Pill tone="bad">Check contamination</Pill>
                      )}
                    </div>
                    <h2 className="font-display mt-3 text-2xl">{detail.sampleId}</h2>
                    <p className="mt-1 text-xs text-muted">
                      {detail.sourceFile} → {detail.targetFile}
                    </p>
                  </div>
                  <div className="text-right text-xs text-muted">
                    {detail.decision?.reviewedAt ? (
                      <p>
                        Saved{" "}
                        {new Date(detail.decision.reviewedAt).toLocaleString("vi-VN")}
                      </p>
                    ) : (
                      <p>Chưa review</p>
                    )}
                    {dirty ? (
                      <p className="mt-1 font-semibold text-[#e8b96d]">
                        Có edit chưa lưu
                      </p>
                    ) : null}
                  </div>
                </div>

                {detail.stale ? (
                  <div className="mt-5 flex gap-2 rounded-xl border border-[#514027] bg-[#332719] px-4 py-3 text-sm font-medium text-[#e8b96d]">
                    <RefreshCw className="mt-0.5 shrink-0" size={15} />
                    Draft nguồn đã đổi sau lần review trước. Kiểm tra lại rồi lưu
                    quyết định mới.
                  </div>
                ) : null}

                {detail.validationErrors.length ? (
                  <div className="mt-5 rounded-xl border border-ember/20 bg-[#321e1a] px-4 py-3">
                    <p className="flex items-center gap-2 text-sm font-semibold text-ember">
                      <ShieldAlert size={16} />
                      Chưa thể approve
                    </p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-ember">
                      {detail.validationErrors.map((message) => (
                        <li key={message}>{message}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {detail.parent ? (
                  <div className="mt-5 rounded-xl border border-[#4d342a] bg-[#291f1a] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-clay">
                        Parent original · {detail.parent.sampleId}
                      </p>
                      <Pill tone={statusTone(detail.parent)}>
                        {statusLabel(detail.parent)}
                      </Pill>
                    </div>
                    <p className="mt-3 text-[15px] leading-7 text-ink/82">
                      {String(detail.parent.row.user_query ?? "")}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-muted">
                      {String(detail.parent.row.expected_behavior ?? "")}
                    </p>
                  </div>
                ) : null}

                <div className="mt-6 space-y-5">
                  <ReviewSection
                    title="Nội dung người dùng"
                    description="Đọc như một câu hỏi thật; chỉnh nếu câu bị máy móc hoặc đổi nghĩa."
                  >
                    <EditorLabel label="User query" required>
                      <textarea
                        value={form.userQuery}
                        onChange={(event) =>
                          updateForm("userQuery", event.target.value)
                        }
                        className={`${inputClass} min-h-32 resize-y text-[15px] leading-7`}
                      />
                    </EditorLabel>
                  </ReviewSection>

                  <ReviewSection
                    title="Nhãn đánh giá"
                    description="Đảm bảo task, intent, chủ thể và risk khớp đúng nội dung."
                  >
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                      <EditorLabel label="Task type" required>
                        <select
                          value={form.taskType}
                          onChange={(event) =>
                            updateForm("taskType", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="advise">advise</option>
                          <option value="clarify">clarify</option>
                          <option value="knowledge">knowledge</option>
                          <option value="safety">safety</option>
                          <option value="multi_turn">multi_turn</option>
                          <option value="ood">ood</option>
                          <option value="adversarial">adversarial</option>
                        </select>
                      </EditorLabel>
                      <EditorLabel label="Intent">
                        <select
                          value={form.intentLabel}
                          onChange={(event) =>
                            updateForm("intentLabel", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">—</option>
                          <option value="advise">advise</option>
                          <option value="clarify">clarify</option>
                          <option value="knowledge">knowledge</option>
                          <option value="reject">reject</option>
                        </select>
                      </EditorLabel>
                      <EditorLabel label="Subject">
                        <select
                          value={form.subjectLabel}
                          onChange={(event) =>
                            updateForm("subjectLabel", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">—</option>
                          <option value="self">self</option>
                          <option value="other">other</option>
                          <option value="general">general</option>
                        </select>
                      </EditorLabel>
                      <EditorLabel label="Risk">
                        <select
                          value={form.riskLevel}
                          onChange={(event) =>
                            updateForm("riskLevel", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">—</option>
                          <option value="low">low</option>
                          <option value="medium">medium</option>
                          <option value="high">high</option>
                          <option value="critical">critical</option>
                        </select>
                      </EditorLabel>
                      <EditorLabel label="Difficulty">
                        <select
                          value={form.difficulty}
                          onChange={(event) =>
                            updateForm("difficulty", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">—</option>
                          <option value="easy">easy</option>
                          <option value="medium">medium</option>
                          <option value="hard">hard</option>
                        </select>
                      </EditorLabel>
                    </div>
                  </ReviewSection>

                  <ReviewSection
                    title="Gold expectations"
                    description="Mô tả hành vi đúng và các giới hạn model tuyệt đối không được vượt."
                  >
                    <div className="space-y-4">
                      <EditorLabel label="Expected behavior" required>
                        <textarea
                          value={form.expectedBehavior}
                          onChange={(event) =>
                            updateForm("expectedBehavior", event.target.value)
                          }
                          className={`${inputClass} min-h-28 resize-y leading-7`}
                        />
                      </EditorLabel>
                      <div className="grid gap-4 lg:grid-cols-2">
                        <EditorLabel
                          label="Expected answer points"
                          hint="Mỗi dòng là một point"
                          required
                        >
                          <textarea
                            value={form.expectedAnswerPoints}
                            onChange={(event) =>
                              updateForm(
                                "expectedAnswerPoints",
                                event.target.value,
                              )
                            }
                            className={`${inputClass} min-h-44 resize-y leading-7`}
                          />
                        </EditorLabel>
                        <EditorLabel
                          label="Forbidden claims"
                          hint="Mỗi dòng là một claim bị cấm"
                        >
                          <textarea
                            value={form.forbiddenClaims}
                            onChange={(event) =>
                              updateForm("forbiddenClaims", event.target.value)
                            }
                            className={`${inputClass} min-h-44 resize-y leading-7`}
                          />
                        </EditorLabel>
                      </div>
                    </div>
                  </ReviewSection>

                  <ReviewSection
                    title="Context và metadata"
                    description="History quan trọng với D5; tags giúp kiểm tra độ phủ scenario."
                  >
                    <div className="space-y-4">
                      <EditorLabel
                        label="Conversation history"
                        hint="JSON array; đặc biệt quan trọng với D5"
                      >
                        <textarea
                          value={form.conversationHistory}
                          onChange={(event) =>
                            updateForm(
                              "conversationHistory",
                              event.target.value,
                            )
                          }
                          spellCheck={false}
                          className={`${inputClass} min-h-52 resize-y font-mono text-xs leading-5`}
                        />
                      </EditorLabel>
                      <div className="grid gap-4 lg:grid-cols-2">
                        <EditorLabel
                          label="Scenario tags"
                          hint="Mỗi dòng là một tag"
                        >
                          <textarea
                            value={form.scenarioTags}
                            onChange={(event) =>
                              updateForm("scenarioTags", event.target.value)
                            }
                            className={`${inputClass} min-h-28 resize-y leading-7`}
                          />
                        </EditorLabel>
                        <EditorLabel
                          label="Reference answer"
                          hint="Có thể để trống"
                        >
                          <textarea
                            value={form.referenceAnswer}
                            onChange={(event) =>
                              updateForm("referenceAnswer", event.target.value)
                            }
                            className={`${inputClass} min-h-28 resize-y leading-7`}
                          />
                        </EditorLabel>
                      </div>
                    </div>
                  </ReviewSection>

                  <ReviewSection
                    title="Quyết định của reviewer"
                    description="Ghi ngắn gọn lý do chỉnh sửa hoặc reject để audit về sau."
                  >
                    <EditorLabel label="Human review notes">
                      <textarea
                        value={form.humanNotes}
                        onChange={(event) =>
                          updateForm("humanNotes", event.target.value)
                        }
                        placeholder="Ví dụ: Đã kiểm tra risk và expected behavior; typo giữ nguyên intent."
                        className={`${inputClass} min-h-24 resize-y leading-7`}
                      />
                    </EditorLabel>
                  </ReviewSection>

                  <details className="rounded-xl border border-line bg-sand/35">
                    <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-ink/75">
                      Source JSON và generation metadata
                    </summary>
                    <pre className="max-h-[520px] overflow-auto border-t border-line p-4 text-[11px] leading-5 text-ink/75">
                      {pretty(detail.sourceRow)}
                    </pre>
                  </details>
                </div>
              </Card>

              <Card className="p-5">
                <div className="flex items-center gap-2">
                  <Sparkles size={18} className="text-clay" />
                  <h3 className="font-display text-xl">
                    Checklist {detail.datasetKey.toUpperCase()}
                  </h3>
                </div>
                <ul className="mt-4 grid gap-3 text-sm leading-6 text-ink/70 lg:grid-cols-3">
                  {REVIEW_GUIDES[detail.datasetKey].map((guide) => (
                    <li
                      key={guide}
                      className="flex gap-2 rounded-xl border border-line/70 bg-sand/35 px-3.5 py-3.5"
                    >
                      <Check className="mt-1 shrink-0 text-clay" size={14} />
                      {guide}
                    </li>
                  ))}
                </ul>
              </Card>

              <div className="sticky bottom-4 z-20 rounded-2xl border border-line bg-panel/95 p-3 shadow-panel backdrop-blur-xl">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="px-2 text-xs font-medium text-muted">
                    Phím tắt khi không focus input: A approve · E edit · R reject
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="ghost"
                      disabled={saving}
                      onClick={() => void saveDecision("pending")}
                    >
                      <RotateCcw size={15} />
                      Reset
                    </Button>
                    <Button
                      variant="danger"
                      disabled={saving}
                      onClick={() => void saveDecision("rejected")}
                    >
                      <X size={16} />
                      Reject (R)
                    </Button>
                    <button
                      disabled={saving}
                      onClick={() => void saveDecision("needs_edit")}
                      className="inline-flex items-center justify-center gap-2 rounded-[10px] bg-[#d8a34f] px-4 py-2.5 text-sm font-semibold text-[#3f321d] shadow-sm transition hover:bg-[#c9923f] disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      <FilePenLine size={16} />
                      Needs edit (E)
                    </button>
                    <Button
                      variant="success"
                      disabled={saving}
                      onClick={() => void saveDecision("approved")}
                    >
                      <Check size={16} />
                      {saving ? "Saving…" : "Approve (A)"}
                    </Button>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <Card className="p-6">
              <EmptyState
                title={
                  detailLoading ? "Đang tải sample…" : "Chọn một sample để review"
                }
                description="Bạn sẽ thấy query, labels, expected behavior, history, parent typo và các nút approve/edit/reject."
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function SummaryCard({
  label,
  value,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const tones = {
    neutral: "bg-panel text-ink border-line",
    good: "bg-[#1e2b22] text-moss border-[#304536]",
    warn: "bg-[#332719] text-[#e8b96d] border-[#514027]",
    bad: "bg-[#321e1a] text-ember border-[#523029]",
  };
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted">
          {label}
        </span>
        <span className="opacity-80">{icon}</span>
      </div>
      <p className="font-display mt-2 text-3xl leading-none">{value}</p>
    </div>
  );
}

function FilterLabel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="text-[13px] font-medium text-ink/70">
      <span className="mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function EditorLabel({
  label,
  hint,
  required = false,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-[13px] font-medium text-ink/75">
      <span className="mb-1.5 flex flex-wrap items-center gap-2">
        {label}
        {required ? <span className="text-ember">*</span> : null}
        {hint ? (
          <span className="font-normal text-muted">{hint}</span>
        ) : null}
      </span>
      {children}
    </label>
  );
}

function ReviewSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line/80 bg-sand/25 p-4 sm:p-5">
      <div className="mb-4 border-b border-line/70 pb-3">
        <h3 className="font-display text-lg text-ink">{title}</h3>
        <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
      </div>
      {children}
    </section>
  );
}
