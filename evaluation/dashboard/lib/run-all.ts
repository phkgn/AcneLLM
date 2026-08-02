export const RUN_ALL_STATUSES = [
  "pending",
  "running",
  "ok",
  "fail",
  "skipped",
] as const;

export type RunAllStepStatus = (typeof RUN_ALL_STATUSES)[number];

export interface RunAllStep {
  id: string;
  label: string;
  status: RunAllStepStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  detail: string;
}

export interface RunAllSummary {
  run_id: string;
  out_dir: string;
  started_at: string;
  finished_at: string | null;
  current_step: string | null;
  steps: RunAllStep[];
}

const STATUS_SET = new Set<string>(RUN_ALL_STATUSES);

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

export function parseRunAllSummary(value: unknown): RunAllSummary | null {
  const source = record(value);
  if (
    !source ||
    !nonEmptyString(source.run_id) ||
    !nonEmptyString(source.out_dir) ||
    !nonEmptyString(source.started_at) ||
    !nullableString(source.finished_at) ||
    !nullableString(source.current_step) ||
    !Array.isArray(source.steps)
  ) {
    return null;
  }

  const steps: RunAllStep[] = [];
  const ids = new Set<string>();
  for (const rawStep of source.steps) {
    const step = record(rawStep);
    if (
      !step ||
      !nonEmptyString(step.id) ||
      !nonEmptyString(step.label) ||
      !nonEmptyString(step.status) ||
      !STATUS_SET.has(step.status) ||
      !nullableString(step.started_at) ||
      !nullableString(step.finished_at) ||
      typeof step.detail !== "string" ||
      !(
        step.duration_s === null ||
        (typeof step.duration_s === "number" &&
          Number.isFinite(step.duration_s) &&
          step.duration_s >= 0)
      ) ||
      ids.has(step.id)
    ) {
      return null;
    }
    ids.add(step.id);
    steps.push({
      id: step.id,
      label: step.label,
      status: step.status as RunAllStepStatus,
      started_at: step.started_at,
      finished_at: step.finished_at,
      duration_s: step.duration_s,
      detail: step.detail,
    });
  }

  if (!steps.length || (source.current_step && !ids.has(source.current_step))) {
    return null;
  }

  return {
    run_id: source.run_id,
    out_dir: source.out_dir,
    started_at: source.started_at,
    finished_at: source.finished_at,
    current_step: source.current_step,
    steps,
  };
}

export function parseRunAllSummaryText(text: string): RunAllSummary | null {
  try {
    return parseRunAllSummary(JSON.parse(text));
  } catch {
    return null;
  }
}

export function runAllSummaryPath(outDir: unknown): string | null {
  if (typeof outDir !== "string" || !outDir.trim()) return null;
  return `${outDir.trim().replace(/[\\/]+$/, "")}/summary.json`;
}

export function runAllStepPosition(summary: RunAllSummary): number | null {
  if (!summary.current_step) return null;
  const index = summary.steps.findIndex((step) => step.id === summary.current_step);
  return index < 0 ? null : index + 1;
}
