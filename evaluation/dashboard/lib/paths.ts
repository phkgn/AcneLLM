import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";

export class EvaluationPathAccessError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvaluationPathAccessError";
  }
}

function locateRepoRoot(): string {
  let current = path.resolve(process.cwd());
  for (let depth = 0; depth < 6; depth += 1) {
    if (fs.existsSync(path.join(current, "evaluation", "full_evaluation.py"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return path.resolve(process.cwd(), "..", "..");
}

export const REPO_ROOT = locateRepoRoot();
export const EVALUATION_ROOT = path.join(REPO_ROOT, "evaluation");
export const DASHBOARD_ROOT = path.join(EVALUATION_ROOT, "dashboard");
export const REPORTS_ROOT = path.join(EVALUATION_ROOT, "reports");
export const LOGS_ROOT = path.join(DASHBOARD_ROOT, "logs");
export const JOBS_FILE = path.join(DASHBOARD_ROOT, ".jobs.json");
export const DATASET_REVIEWS_FILE = path.join(
  DASHBOARD_ROOT,
  ".dataset-reviews.json",
);
export const DATASET_REVIEWS_BACKUP_FILE = path.join(
  DASHBOARD_ROOT,
  ".dataset-reviews.backup.json",
);
const WHITELISTED_REPO_VISUALS: Record<string, string> = {
  "acnellm_pipeline.html": path.join(REPO_ROOT, "acnellm_pipeline.html"),
  "pipeline_simulator.html": path.join(REPO_ROOT, "pipeline_simulator.html"),
};

export function isPathInside(parent: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

export function resolveEvaluationPath(input: string): string {
  if (!input || input.includes("\0") || path.isAbsolute(input)) {
    throw new EvaluationPathAccessError("Đường dẫn không hợp lệ.");
  }
  const portable = input.replace(/[\\/]+/g, path.sep);
  const prefix = `evaluation${path.sep}`;
  const relative = portable.toLowerCase().startsWith(prefix)
    ? portable.slice(prefix.length)
    : portable;
  const resolved = path.resolve(EVALUATION_ROOT, relative);
  if (!isPathInside(EVALUATION_ROOT, resolved)) {
    throw new EvaluationPathAccessError(
      "Đường dẫn phải nằm bên trong evaluation/.",
    );
  }
  return resolved;
}

export async function resolveWhitelistedRepoVisual(
  input: string,
): Promise<string | null> {
  const normalized = input.replace(/[\\/]+/g, "/");
  const candidate = WHITELISTED_REPO_VISUALS[normalized];
  if (!candidate) return null;
  const [realRepoRoot, realCandidate] = await Promise.all([
    fsp.realpath(REPO_ROOT),
    fsp.realpath(candidate),
  ]);
  if (!isPathInside(realRepoRoot, realCandidate)) {
    throw new EvaluationPathAccessError(
      "Visual whitelist trỏ ra ngoài repository.",
    );
  }
  return realCandidate;
}

export async function assertRealPathInsideEvaluation(
  candidate: string,
): Promise<string> {
  let existing = candidate;
  while (!fs.existsSync(existing)) {
    const parent = path.dirname(existing);
    if (parent === existing) break;
    existing = parent;
  }
  const [realEvaluationRoot, realExisting] = await Promise.all([
    fsp.realpath(EVALUATION_ROOT),
    fsp.realpath(existing),
  ]);
  if (!isPathInside(realEvaluationRoot, realExisting)) {
    throw new EvaluationPathAccessError(
      "Đường dẫn symlink ra ngoài evaluation/ bị chặn.",
    );
  }
  if (fs.existsSync(candidate)) {
    const realCandidate = await fsp.realpath(candidate);
    if (!isPathInside(realEvaluationRoot, realCandidate)) {
      throw new EvaluationPathAccessError(
        "Đường dẫn symlink ra ngoài evaluation/ bị chặn.",
      );
    }
    return realCandidate;
  }
  return candidate;
}

export function toRepoRelative(absolutePath: string): string {
  return path.relative(REPO_ROOT, absolutePath).split(path.sep).join("/");
}

export function toEvaluationRelative(absolutePath: string): string {
  return path.relative(EVALUATION_ROOT, absolutePath).split(path.sep).join("/");
}

export function assertSafeName(value: string, label = "Tên"): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(value)) {
    throw new Error(`${label} không hợp lệ.`);
  }
  return value;
}
