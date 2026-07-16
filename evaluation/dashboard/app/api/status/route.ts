import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { REPO_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Check {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
  fix: string;
}

async function exists(relativePath: string): Promise<boolean> {
  return fs
    .access(path.join(REPO_ROOT, relativePath))
    .then(() => true)
    .catch(() => false);
}

export async function GET() {
  let ollamaReachable = false;
  let tags = new Set<string>();
  try {
    const response = await fetch("http://localhost:11434/api/tags", {
      signal: AbortSignal.timeout(4_000),
      cache: "no-store",
    });
    if (response.ok) {
      ollamaReachable = true;
      const body = (await response.json()) as {
        models?: Array<{ name?: string }>;
      };
      const raw = (body.models ?? [])
        .map((model) => model.name)
        .filter((name): name is string => Boolean(name));
      tags = new Set(raw.flatMap((name) => [name, name.split(":")[0]]));
    }
  } catch {
    ollamaReachable = false;
  }

  const env = await fs
    .readFile(path.join(REPO_ROOT, ".env"), "utf8")
    .catch(() => "");
  const hasJudgeKey = /^\s*DEEPSEEK_API_KEY\s*=\s*[^#\s].*$/m.test(env);
  const checks: Check[] = [
    {
      id: "ollama",
      label: "Ollama API",
      ok: ollamaReachable,
      detail: ollamaReachable
        ? `${tags.size} model tags được phát hiện`
        : "Không phản hồi tại localhost:11434",
      fix: "ollama serve",
    },
    {
      id: "model_finetuned",
      label: "Model acnellm-v2-q4",
      ok: tags.has("acnellm-v2-q4"),
      detail: tags.has("acnellm-v2-q4") ? "Đã sẵn sàng" : "Chưa có trong Ollama",
      fix: "ollama create acnellm-v2-q4 -f model/Modelfile",
    },
    {
      id: "model_base",
      label: "Model qwen25-base-acnesys",
      ok: tags.has("qwen25-base-acnesys"),
      detail: tags.has("qwen25-base-acnesys")
        ? "Đã sẵn sàng"
        : "Chưa có trong Ollama",
      fix: "python evaluation/scripts/make_base_modelfile.py && ollama create qwen25-base-acnesys -f evaluation/modelfiles/qwen25-base-acnesys/Modelfile",
    },
    {
      id: "chroma",
      label: "Chroma knowledge base",
      ok: await exists("data/chroma_db"),
      detail: (await exists("data/chroma_db")) ? "data/chroma_db tồn tại" : "Thiếu data/chroma_db",
      fix: "git lfs pull",
    },
    {
      id: "bm25",
      label: "BM25 index",
      ok: await exists("data/bm25_index.pkl"),
      detail: (await exists("data/bm25_index.pkl"))
        ? "data/bm25_index.pkl tồn tại"
        : "Thiếu data/bm25_index.pkl",
      fix: "python scripts/build_kb.py --step bm25",
    },
    {
      id: "dataset_intent",
      label: "T1 intent dataset",
      ok: await exists("evaluation/datasets/v1/t1_intent_seed.jsonl"),
      detail: "evaluation/datasets/v1/t1_intent_seed.jsonl",
      fix: "python -m evaluation.datasets.build_seeds",
    },
    {
      id: "dataset_guardrails",
      label: "T1 guardrails dataset",
      ok: await exists("evaluation/datasets/v1/t1_guardrails_seed.jsonl"),
      detail: "evaluation/datasets/v1/t1_guardrails_seed.jsonl",
      fix: "python -m evaluation.datasets.build_seeds",
    },
    {
      id: "dataset_qrels",
      label: "T2 qrels dataset",
      ok: await exists("evaluation/datasets/v1/d8_qrels_seed.jsonl"),
      detail: "evaluation/datasets/v1/d8_qrels_seed.jsonl",
      fix: "python -m evaluation.datasets.build_seeds",
    },
    {
      id: "dataset_t3",
      label: "T3 main dataset",
      ok: await exists("evaluation/datasets/v1/d2_test.jsonl"),
      detail: (await exists("evaluation/datasets/v1/d2_test.jsonl"))
        ? "evaluation/datasets/v1/d2_test.jsonl"
        : "D2 chưa được tạo; smoke có thể dùng D1 qua Run all",
      fix: "Tạo và freeze evaluation/datasets/v1/d2_test.jsonl theo blueprint",
    },
    {
      id: "judge_key",
      label: "DeepSeek judge key",
      ok: hasJudgeKey,
      detail: hasJudgeKey
        ? "DEEPSEEK_API_KEY đã được cấu hình"
        : "Không tìm thấy key có giá trị trong .env",
      fix: "Thêm DEEPSEEK_API_KEY vào .env hoặc skip judge",
    },
  ];

  return NextResponse.json({
    checkedAt: new Date().toISOString(),
    ready: checks.every((check) => check.ok),
    checks,
  });
}
