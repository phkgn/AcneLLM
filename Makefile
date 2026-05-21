.PHONY: install pull-models crawl build-dataset serve eval test clean

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	pip install -e .

pull-models:
	ollama pull qwen3:4b
	ollama pull qwen3:1.7b

# ── Data pipeline (LLM Finetune phase) ────────────────────────────────────────
crawl:
	python -m scripts.crawl_all

# Generate Q&A fine-tuning pairs from crawled documents
build-dataset:
	python -m scripts.build_qa_dataset

# ── Serve ──────────────────────────────────────────────────────────────────────
serve:
	uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload

# ── Eval & Test ───────────────────────────────────────────────────────────────
eval:
	python -m scripts.run_eval --n $(or $(N),20)

test:
	pytest -v

# ── Clean ──────────────────────────────────────────────────────────────────────
clean:
	rm -rf data/raw/* data/finetune/* data/chroma_db/* data/bm25_index.pkl

clean-logs:
	rm -rf data/logs/*.log data/logs/*.json
