export type JudgeCalibrationStatus = {
  available: boolean;
  calibrated: boolean;
  failedChecks: string[];
};

export function summarizeJudgeCalibration(
  artifact: unknown,
): JudgeCalibrationStatus {
  if (!artifact || typeof artifact !== "object" || Array.isArray(artifact)) {
    return {
      available: false,
      calibrated: false,
      failedChecks: ["missing"],
    };
  }

  const checks = Object.entries(artifact as Record<string, unknown>)
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
  };
}
