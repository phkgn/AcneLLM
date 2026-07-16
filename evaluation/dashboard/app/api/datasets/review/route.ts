import { NextResponse } from "next/server";
import {
  DATASET_CONFIG,
  DATASET_KEYS,
  REVIEW_STATUSES,
  type DatasetKey,
  type ReviewItem,
  loadReviewItems,
  saveReviewDecision,
  summarizeReview,
} from "@/lib/dataset-review";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseDataset(value: string | null): DatasetKey | "all" {
  if (!value || value === "all") return "all";
  if (DATASET_KEYS.includes(value as DatasetKey)) return value as DatasetKey;
  throw new Error("Dataset filter không hợp lệ.");
}

function serializeListItem(item: ReviewItem) {
  return {
    sampleId: String(item.row.sample_id ?? ""),
    datasetKey: item.datasetKey,
    sourceFile: item.sourceFile,
    query: String(item.row.user_query ?? ""),
    taskType: String(item.row.task_type ?? ""),
    intentLabel: item.row.intent_label ?? null,
    riskLevel: item.row.clinical_risk_level ?? null,
    difficulty: item.row.difficulty ?? null,
    parentSampleId:
      typeof item.row.parent_sample_id === "string"
        ? item.row.parent_sample_id
        : null,
    isVariant: Boolean(item.row.parent_sample_id),
    status: item.status,
    stale: item.stale,
    edited: item.edited,
    reviewedAt: item.decision?.reviewedAt ?? null,
    validationErrorCount: item.validationErrors.length,
  };
}

function serializeDetail(item: ReviewItem, parent: ReviewItem | null) {
  return {
    ...serializeListItem(item),
    targetFile: item.targetFile,
    row: item.row,
    sourceRow: item.sourceRow,
    sourceHash: item.sourceHash,
    decision: item.decision,
    validationErrors: item.validationErrors,
    parent: parent
      ? {
          ...serializeListItem(parent),
          row: parent.row,
        }
      : null,
  };
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const items = await loadReviewItems();
    const sampleId = url.searchParams.get("sampleId");
    if (sampleId) {
      const item = items.find(
        (candidate) => String(candidate.row.sample_id) === sampleId,
      );
      if (!item) {
        return NextResponse.json(
          { error: `Không tìm thấy sample_id ${sampleId}.` },
          { status: 404 },
        );
      }
      const parentId =
        typeof item.row.parent_sample_id === "string"
          ? item.row.parent_sample_id
          : null;
      const parent = parentId
        ? items.find(
            (candidate) => String(candidate.row.sample_id) === parentId,
          ) ?? null
        : null;
      return NextResponse.json(serializeDetail(item, parent));
    }

    const dataset = parseDataset(url.searchParams.get("dataset"));
    const status = url.searchParams.get("status") ?? "all";
    if (
      status !== "all" &&
      status !== "stale" &&
      !REVIEW_STATUSES.includes(status as (typeof REVIEW_STATUSES)[number])
    ) {
      throw new Error("Status filter không hợp lệ.");
    }
    const kind = url.searchParams.get("kind") ?? "all";
    if (!["all", "original", "variant"].includes(kind)) {
      throw new Error("Kind filter không hợp lệ.");
    }
    const query = (url.searchParams.get("query") ?? "")
      .trim()
      .toLocaleLowerCase("vi");
    const requestedPage = Math.max(
      1,
      Number(url.searchParams.get("page") ?? 1) || 1,
    );
    const pageSize = Math.min(
      100,
      Math.max(10, Number(url.searchParams.get("pageSize") ?? 50) || 50),
    );

    const filtered = items.filter((item) => {
      if (dataset !== "all" && item.datasetKey !== dataset) return false;
      if (status === "stale" && !item.stale) return false;
      if (
        status !== "all" &&
        status !== "stale" &&
        (item.stale || item.status !== status)
      ) {
        return false;
      }
      const isVariant = Boolean(item.row.parent_sample_id);
      if (kind === "variant" && !isVariant) return false;
      if (kind === "original" && isVariant) return false;
      if (query) {
        const haystack = [
          item.row.sample_id,
          item.row.user_query,
          item.row.expected_behavior,
          ...(Array.isArray(item.row.scenario_tags)
            ? item.row.scenario_tags
            : []),
        ]
          .join("\n")
          .toLocaleLowerCase("vi");
        if (!haystack.includes(query)) return false;
      }
      return true;
    });

    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const page = Math.min(requestedPage, totalPages);
    const byDataset = Object.fromEntries(
      DATASET_KEYS.map((key) => [
        key,
        {
          ...DATASET_CONFIG[key],
          ...summarizeReview(
            items.filter((candidate) => candidate.datasetKey === key),
          ),
        },
      ]),
    );
    return NextResponse.json({
      dataset,
      filters: { status, kind, query },
      summary: summarizeReview(items),
      byDataset,
      total: filtered.length,
      page,
      pageSize,
      totalPages,
      rows: filtered
        .slice((page - 1) * pageSize, page * pageSize)
        .map(serializeListItem),
    });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as JsonRecord;
    const sampleId = String(body.sampleId ?? "").trim();
    const status = String(body.status ?? "");
    if (!/^[a-zA-Z0-9._-]+$/.test(sampleId)) {
      throw new Error("sampleId không hợp lệ.");
    }
    if (!REVIEW_STATUSES.includes(status as (typeof REVIEW_STATUSES)[number])) {
      throw new Error("Review status không hợp lệ.");
    }
    if (body.editedFields !== undefined && !isRecord(body.editedFields)) {
      throw new Error("editedFields phải là object.");
    }
    const item = await saveReviewDecision({
      sampleId,
      status: status as (typeof REVIEW_STATUSES)[number],
      humanNotes: String(body.humanNotes ?? ""),
      editedFields: isRecord(body.editedFields) ? body.editedFields : {},
    });
    return NextResponse.json(serializeDetail(item, null));
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
