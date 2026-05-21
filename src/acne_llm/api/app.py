from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from loguru import logger

# ensure package path works when running `uvicorn acne_llm.api.app:app`
import sys
ROOT = Path(__file__).resolve().parents[3]  # .../AcneLLM
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from acne_llm.di import build_container  # noqa: E402
from acne_llm.api.routes import chat, kb, health, metrics  # noqa: E402
from acne_llm.api.observability import (  # noqa: E402
    APIKeyMiddleware,
    MetricsRegistry,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
)
from acne_llm.utils.logging import configure_logging  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("🚀 AcneLLM starting…")
    app.state.container = build_container(settings)
    logger.info("✅ AcneLLM ready")
    yield
    await app.state.container.close()
    logger.info("👋 AcneLLM stopped")


app = FastAPI(
    title="AcneLLM API",
    version="0.1.0",
    description="Hệ thống tư vấn da mụn tiếng Việt — local RAG + LLM",
    lifespan=lifespan,
)

app.state.metrics = MetricsRegistry()

cors_origins = list(settings.cors_origins)
if "*" not in cors_origins and settings.frontend_url not in cors_origins:
    cors_origins.append(settings.frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.add_middleware(RequestLoggingMiddleware, metrics=app.state.metrics)
app.add_middleware(APIKeyMiddleware, api_key=settings.api_key)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url=settings.frontend_url, status_code=307)

app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(kb.router, prefix="/api/v1")
app.include_router(metrics.router)
