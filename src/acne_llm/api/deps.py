from fastapi import Request, HTTPException
from ..di import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_hybrid_pipeline(request: Request):
    c: Container = request.app.state.container
    if c.hybrid is None:
        raise HTTPException(
            status_code=503,
            detail="RAG not ready. Run: python scripts/build_kb.py --step embed",
        )
    return c.hybrid


def get_pipeline_for(mode: str, request: Request):
    c: Container = request.app.state.container
    if mode == "hybrid" and not c.rag_ready:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Pipeline '{mode}' requires RAG index. "
                f"Run: python scripts/build_kb.py --step embed"
            ),
        )
    pipeline_map = {
        "llm_only": c.llm_only,
        "hybrid": c.hybrid,
    }
    return pipeline_map.get(mode, c.llm_only)
