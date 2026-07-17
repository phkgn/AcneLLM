export type JudgeCalibrationStatus = {
  available: boolean;
  calibrated: boolean;
  failedChecks: string[];
  provider: string | null;
  model: string | null;
};

export function summarizeJudgeCalibration(
  artifact: unknown,
): JudgeCalibrationStatus {
  if (!artifact || typeof artifact !== "object" || Array.isArray(artifact)) {
    return {
      available: false,
      calibrated: false,
      failedChecks: ["missing"],
      provider: null,
      model: null,
    };
  }

  const record = artifact as Record<string, unknown>;
  const checks = Object.entries(record)
    .filter(([, value]) => value && typeof value === "object" && !Array.isArray(value))
    .map(([name, value]) => ({
      name,
      pass: (value as Record<string, unknown>).pass,
    }))
    .filter((check) => typeof check.pass === "boolean");
  const failedChecks = checks
    .filter((check) => check.pass !== true)
    .map((check) => check.name);
  return {
    available: true,
    calibrated: checks.length > 0 && failedChecks.length === 0,
    failedChecks: checks.length ? failedChecks : ["invalid"],
    provider: typeof record.judge_provider === "string" ? record.judge_provider : null,
    model: typeof record.judge_model === "string" ? record.judge_model : null,
  };
}
