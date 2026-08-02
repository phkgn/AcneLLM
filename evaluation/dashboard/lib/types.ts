export type CommandId =
  | "full_evaluation"
  | "retrieval_eval"
  | "answer_generation"
  | "llm_scoring"
  | "build_report"
  | "quality_gate"
  | "trust_audit"
  | "figures_kb"
  | "figures_eval"
  | "figures_usage"
  | "figures_all"
  | "intake_eval"
  | "bottleneck_analysis"
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
