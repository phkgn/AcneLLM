import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { REPO_ROOT } from "@/lib/paths";
import { summarizeOllamaModels } from "@/lib/status";

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
  let modelCount = 0;
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
      const summary = summarizeOllamaModels(body.models ?? []);
      modelCount = summary.modelCount;
      tags = summary.lookupNames;
    }
  } catch {
    ollamaReachable = false;
  }

  const env = await fs
    .readFile(path.join(REPO_ROOT, ".env"), "utf8")
    .catch(() => "");
  const hasJudgeKey =
    Boolean(process.env.OPENAI_API_KEY?.trim()) ||
    /^\s*OPENAI_API_KEY\s*=\s*[^#\s].*$/m.test(env);
  const answerQualityFinalExists = await exists(
    "evaluation/datasets/v1/answer_quality_test.jsonl",
  );
  const answerQualityDraftExists = await exists(
    "evaluation/datasets/drafts/v1/answer_quality_test.draft.jsonl",
  );
  const checks: Check[] = [
    {
      id: "ollama",
      label: "Ollama API",
      ok: ollamaReachable,
      detail: ollamaReachable
        ? `${modelCount} model tags được phát hiện`
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
      id: "dataset_qrels",
      label: "Bộ test tìm kiếm tài liệu",
      ok: await exists("evaluation/datasets/v1/retrieval_test.jsonl"),
      detail: "evaluation/datasets/v1/retrieval_test.jsonl",
      fix: "python -m evaluation.datasets.build_seeds",
    },
    {
      id: "dataset_t3",
      label: "Bộ test chất lượng câu trả lời",
      ok: answerQualityFinalExists,
      detail: answerQualityFinalExists
        ? "evaluation/datasets/v1/answer_quality_test.jsonl"
        : answerQualityDraftExists
          ? "Draft chất lượng câu trả lời đã có nhưng chưa export sang datasets/v1"
          : "Chưa có draft hoặc bản final; smoke có thể dùng bộ dev",
      fix: answerQualityDraftExists
        ? "Dataset review → chọn Chất lượng câu trả lời → Export"
        : "Sinh draft, human-review rồi export bộ chất lượng câu trả lời",
    },
    {
      id: "judge_key",
      label: "OpenAI judge key",
      ok: hasJudgeKey,
      detail: hasJudgeKey
        ? "OPENAI_API_KEY đã cấu hình · judge và faithfulness theo Python"
        : "Không tìm thấy key có giá trị trong .env",
      fix: "Thêm OPENAI_API_KEY vào .env hoặc skip judge",
    },
  ];

  return NextResponse.json({
    checkedAt: new Date().toISOString(),
    ready: checks.every((check) => check.ok),
    checks,
  });
}
