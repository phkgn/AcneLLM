"""Compare Vietnamese and English retrieval reachability through live KB API."""
from __future__ import annotations

import json
from pathlib import Path
import time

import httpx
import chromadb


BASE = "http://localhost:8000"
OUT = Path(__file__).with_name("retrieval_probes.json")
QUERIES = {
    "moderate_acne_vi": "mụn viêm mức độ vừa điều trị ban đầu theo guideline AAD NICE",
    "moderate_acne_en": "moderate inflammatory acne initial treatment AAD NICE guideline",
    "pregnancy_vi": "mang thai mụn viêm azelaic acid benzoyl peroxide an toàn tránh retinoid",
    "pregnancy_en": "pregnancy inflammatory acne azelaic acid benzoyl peroxide safety avoid retinoids guideline",
    "topical_interaction_vi": "benzoyl peroxide làm giảm tác dụng tretinoin hay chỉ tăng kích ứng",
    "topical_interaction_en": "benzoyl peroxide tretinoin degradation stability irritation interaction",
}


def main() -> None:
    result = {"base_url": BASE, "queries": []}
    collection = chromadb.PersistentClient(path="./data/chroma_db").get_collection("acne_kb_vi")
    with httpx.Client(timeout=180) as client:
        for name, query in QUERIES.items():
            row = {"name": name, "query": query, "modes": {}}
            for mode in ("dense", "sparse", "hybrid"):
                started = time.perf_counter()
                response = client.post(
                    f"{BASE}/api/v1/kb/retrieve",
                    json={"query": query, "top_k": 10, "mode": mode},
                )
                response.raise_for_status()
                body = response.json()
                chunks = body.get("chunks", [])
                chunk_ids = [chunk["chunk_id"] for chunk in chunks]
                got = collection.get(ids=chunk_ids, include=["metadatas"])
                metadata_by_id = {
                    str(cid): (metadata or {})
                    for cid, metadata in zip(got.get("ids") or [], got.get("metadatas") or [])
                }
                for chunk in chunks:
                    metadata = metadata_by_id.get(str(chunk["chunk_id"]), {})
                    chunk["source_type"] = metadata.get("source_type", "unknown")
                    chunk["lang"] = metadata.get("lang", "unknown")
                    chunk["title"] = metadata.get("title", "")
                    chunk["url"] = metadata.get("url", "")
                    chunk["text"] = chunk.get("text", "")[:500]
                row["modes"][mode] = {
                    "wall_time_ms": int((time.perf_counter() - started) * 1000),
                    "chunks": chunks,
                }
                OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            result["queries"].append(row)
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(name, flush=True)


if __name__ == "__main__":
    main()
