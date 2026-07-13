"""CLI entrypoint: acne-llm {chat, serve, stats}."""
from __future__ import annotations
import json
import typer
from rich import print as rprint

app = typer.Typer(help="AcneLLM CLI")


@app.command()
def chat(description: str, mode: str = "auto", age: int = None,
         skin_type: str = None, pregnant: bool = False):
    """Send a single query through the production chat path; print AdviseOutput as JSON."""
    from acne_llm.config import settings
    from acne_llm.di import build_container
    from acne_llm.chat.orchestrator import prepare_chat_turn, generate_structured
    from acne_llm.schemas import UserInput, UserContext

    c = build_container(settings)
    user_override = UserInput(
        description=description,
        context=UserContext(age=age, skin_type=skin_type, is_pregnant=pregnant),
        mode=mode,
    )
    prepared = prepare_chat_turn(
        c, description, requested_mode=mode,
        response_format="structured", user_override=user_override,
    )
    out = generate_structured(c, prepared)
    rprint(json.loads(out.model_dump_json()))


@app.command()
def stats():
    from acne_llm.config import settings
    from acne_llm.di import build_container
    c = build_container(settings)
    rprint({
        "chroma_chunks": c.store.count(),
        "bm25_chunks": len(c.bm25.chunk_ids) if c.bm25 else 0,
        "ollama_ok": c.llm.health(),
        "model": c.llm.model,
    })


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    import uvicorn
    uvicorn.run("acne_llm.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
