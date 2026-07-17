export type CommandId =
  | "run_all"
  | "preliminary_d2"
  | "t1_normalizer"
  | "t1_intent"
  | "t1_planner"
  | "t1_guardrails"
  | "t2_retrieval"
  | "t3_generation"
  | "judge"
  | "report"
  | "check_gate"
  | "validation_loop"
  | "figures_kb"
  | "figures_eval"
  | "figures_usage"
  | "figures_all"
  | "tests";

export type JobStatus =
  | "running"
  | "stopping"
  | "succeeded"
  | "failed"
  | "killed"
  | "exited";

export interface JobRecord {
  jobId: string;
  pid: number;
  commandId: CommandId;
  command: string;
  argv: string[];
  args: Record<string, unknown>;
  startedAt: string;
  finishedAt?: string;
  status: JobStatus;
  exitCode: number | null;
  signal: string | null;
  logFile: string;
}

export interface CatalogDataset {
  name: string;
  path: string;
  rows: number;
  frozen: boolean;
}

export interface CatalogExperiment {
  name: string;
  path: string;
  dataset: string | null;
  systems: string[];
  exists: boolean;
}

export interface CatalogSystem {
  id: string;
  name: string;
  model: string | null;
  retrieval: boolean;
  path: string;
}
