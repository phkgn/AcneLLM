export const PRELIMINARY_LIMIT_MIN = 30;
export const PRELIMINARY_LIMIT_MAX = 140;
export const PRELIMINARY_LIMIT_DEFAULT = PRELIMINARY_LIMIT_MAX;

export function parsePreliminaryLimit(value: unknown): number {
  if (value === undefined || value === null || value === "") {
    return PRELIMINARY_LIMIT_DEFAULT;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  if (
    !Number.isInteger(parsed) ||
    parsed < PRELIMINARY_LIMIT_MIN ||
    parsed > PRELIMINARY_LIMIT_MAX
  ) {
    throw new Error(
      `Quick Run limit phải là số nguyên từ ${PRELIMINARY_LIMIT_MIN} đến ${PRELIMINARY_LIMIT_MAX}.`,
    );
  }
  return parsed;
}

export function isValidPreliminaryLimitInput(value: string): boolean {
  if (!value.trim()) return false;
  try {
    parsePreliminaryLimit(value);
    return true;
  } catch {
    return false;
  }
}
