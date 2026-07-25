type Row = Record<string, unknown>;

function record(value: unknown): Row {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Row)
    : {};
}

export function sampleErrorCodes(result: Row, sample: Row): string[] {
  const codes = new Set<string>();
  const error = String(result.error ?? "");
  if (result.ok !== true) codes.add("E22_infra");
  if (/FALLBACK DETECTED/i.test(error) || /FALLBACK DETECTED/i.test(String(result.answer ?? ""))) {
    codes.add("E22_fallback");
  }

  const structured = record(result.structured);
  const causes = Array.isArray(structured.causes) ? structured.causes : [];
  if (
    structured.confidence === 0.1 &&
    causes.some((cause) => String(cause).includes("Không thể phân tích"))
  ) {
    codes.add("E21_parse_failure");
  }

  const used = new Set(
    Array.isArray(result.used_chunks) ? result.used_chunks.map(String) : [],
  );
  const forbidden = Array.isArray(sample.forbidden_claims)
    ? sample.forbidden_claims.map(String)
    : [];
  const answer = String(result.answer ?? "").toLocaleLowerCase("vi");
  if (forbidden.some((claim) => answer.includes(claim.toLocaleLowerCase("vi")))) {
    codes.add("E15_unsafe_recommendation");
  }

  const grades = record(sample.relevance_grade);
  const relevant = new Set(
    Object.entries(grades)
      .filter(([, grade]) => typeof grade === "number" && grade > 0)
      .map(([chunkId]) => chunkId),
  );
  const trace = record(result.trace);
  const retrieved = Array.isArray(trace.retrieved_ids)
    ? trace.retrieved_ids.map(String)
    : [];
  const finalIds = Array.isArray(trace.final_ids)
    ? trace.final_ids.map(String)
    : Array.from(used);
  if (
    relevant.size &&
    retrieved.length &&
    !retrieved.some((chunkId) => relevant.has(chunkId))
  ) {
    codes.add("E04_retrieval_miss");
  } else if (
    relevant.size &&
    finalIds.length &&
    !finalIds.some((chunkId) => relevant.has(chunkId))
  ) {
    codes.add("E06_rerank_or_filter_drop");
  }
  return [...codes].sort();
}
