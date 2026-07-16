import path from "node:path";
import { readJsonFile } from "./files.ts";
import { REPORTS_ROOT } from "./paths.ts";

export interface GateCheck {
  section: string;
  metric: string;
  threshold: number;
  value: number | null;
  status: "pass" | "fail";
  source: string;
}

type GateArtifact = {
  n_pass?: unknown;
  n_total?: unknown;
  checks?: unknown;
};

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function normalizeGateArtifact(artifact: unknown) {
  const raw =
    artifact && typeof artifact === "object" && !Array.isArray(artifact)
      ? (artifact as GateArtifact)
      : {};
  const rawChecks = Array.isArray(raw.checks) ? raw.checks : [];
  const checks = rawChecks.flatMap((item): GateCheck[] => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const check = item as Record<string, unknown>;
    if (
      typeof check.name !== "string" ||
      typeof check.pass !== "boolean" ||
      numberOrNull(check.threshold) === null
    ) {
      return [];
    }
    const [section, ...metricParts] = check.name.split(".");
    return [{
      section: section || "gate",
      metric: metricParts.join(".") || check.name,
      threshold: check.threshold as number,
      value: numberOrNull(check.actual),
      status: check.pass ? "pass" : "fail",
      source: "reports/gate_check.json",
    }];
  });
  const reportedPass = numberOrNull(raw.n_pass);
  const reportedTotal = numberOrNull(raw.n_total);
  const pass =
    reportedPass === null
      ? checks.filter((check) => check.status === "pass").length
      : reportedPass;
  const total = reportedTotal === null ? checks.length : reportedTotal;
  return {
    checks,
    summary: {
      pass,
      fail: Math.max(total - pass, 0),
      missing: 0,
    },
  };
}

export async function evaluateGates(experiment?: string) {
  void experiment;
  const artifact = await readJsonFile<Record<string, unknown>>(
    path.join(REPORTS_ROOT, "gate_check.json"),
  );
  return normalizeGateArtifact(artifact);
}
