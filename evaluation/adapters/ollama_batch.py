"""S0–S3 tier T3: batch path qua HybridPipeline / LLMOnlyPipeline (JSON AdviseOutput).

Pipelines dựng trực tiếp từ container components (Container KHÔNG có .hybrid/.llm_only —
legacy scripts/run_eval.py tham chiếu attr không tồn tại; adapter này thay thế).
"""
from __future__ import annotations

from .base import SystemAdapter
from ._repo import build_eval_container, normalize_query


class OllamaBatchAdapter(SystemAdapter):
    def prepare(self) -> None:
        cfg = self.config
        self.container = build_eval_container(cfg["model"], cfg.get("sampling"))
        if cfg.get("retrieval"):
            if not self.container.rag_ready:
                raise RuntimeError("KB chưa sẵn sàng (chroma_db + bm25_index.pkl) "
                                   "nhưng condition yêu cầu retrieval")
            from acne_llm.pipeline.hybrid import HybridPipeline
            self.pipeline = HybridPipeline(
                retriever=self.container.retriever,
                reranker=self.container.reranker,
                llm=self.container.llm,
                prompt=self.container.prompt,
                guardrails=self.container.guardrails,
                retrieve_top_k=cfg.get("retrieve_top_k", 15),
                rerank_top_k=cfg.get("rerank_top_k", 5),
                clinical_planner=self.container.clinical_planner,
                use_mmr_prefilter=cfg.get("use_mmr_prefilter", True),
                mmr_lambda=cfg.get("mmr_lambda", 0.6),
            )
        else:
            from acne_llm.pipeline.llm_only import LLMOnlyPipeline
            self.pipeline = LLMOnlyPipeline(
                llm=self.container.llm,
                prompt=self.container.prompt,
                guardrails=self.container.guardrails,
                clinical_planner=self.container.clinical_planner,
            )
        # Xác nhận model đúng (chống chạy nhầm checkpoint)
        assert self.container.llm.model == cfg["model"], (
            f"Model mismatch: container={self.container.llm.model} config={cfg['model']}"
        )
        # Lookup text theo chunk_id — để judge thấy CONTEXT THẬT (fix faithfulness=0)
        self._chunk_texts: dict[str, str] = {}
        if cfg.get("retrieval") and self.container.bm25 is not None:
            self._chunk_texts = dict(zip(self.container.bm25.chunk_ids,
                                         self.container.bm25.texts))

    def generate(self, sample: dict, context: dict | None) -> dict:
        user, prepared = normalize_query(self.container, sample)
        self._trace["normalized_user"] = user.model_dump(mode="json")
        self._trace["prepared_clean_text"] = prepared.clean_text

        output = self.pipeline.run(user)
        dump = output.model_dump(mode="json")
        self._trace["advise_output"] = dump

        if dump.get("model_name") and dump["model_name"] != self.config["model"]:
            raise RuntimeError(  # R4: fallback lọt qua → invalid record, không im lặng
                f"FALLBACK DETECTED: answered by {dump['model_name']}"
            )
        answer = _flatten_advise(dump)
        used = dump.get("used_chunks", [])
        if used and getattr(self, "_chunk_texts", None):
            self._trace["context_chunks"] = [
                {"chunk_id": cid, "text": self._chunk_texts.get(cid, "")[:1500]}
                for cid in used
            ]
        return {
            "answer": answer,
            "structured": dump,
            "used_chunks": used,
            "model_name": dump.get("model_name"),
        }

    def run(self, sample: dict) -> dict:
        # Batch pipelines tự retrieve bên trong run() → bỏ retrieve() tách rời,
        # trace retrieval lấy từ used_chunks + advise_output.
        cfg_retrieval = self.config.get("retrieval")
        self.config["retrieval"] = False   # tránh base.run gọi retrieve() rỗng
        try:
            return super().run(sample)
        finally:
            self.config["retrieval"] = cfg_retrieval

    def cleanup(self) -> None:
        try:
            self.container.llm.close()
        except Exception:
            pass


def _flatten_advise(d: dict) -> str:
    """AdviseOutput JSON → text đọc được (cho judge/human)."""
    parts: list[str] = []
    if d.get("severity"):
        parts.append(f"Mức độ: {d['severity']}")
    if d.get("acne_type_primary"):
        parts.append(f"Loại mụn chính: {d['acne_type_primary']}")
    for cause in d.get("causes") or []:
        parts.append(f"- Nguyên nhân: {cause}")
    for rec in d.get("recommendations") or []:
        action = rec.get("action", "") if isinstance(rec, dict) else str(rec)
        src = rec.get("source_chunk_id") if isinstance(rec, dict) else None
        parts.append(f"- Khuyến nghị: {action}" + (f" [nguồn: {src}]" if src else ""))
    for rf in d.get("red_flags") or []:
        flag = rf.get("flag", "") if isinstance(rf, dict) else str(rf)
        parts.append(f"- Dấu hiệu cần khám: {flag}")
    if d.get("disclaimer"):
        parts.append(d["disclaimer"])
    return "\n".join(parts)
