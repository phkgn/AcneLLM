from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    settings = request.app.state.container.settings if hasattr(request.app.state, "container") else None
    if settings is not None and not getattr(settings, "metrics_enabled", True):
        return Response(status_code=404)
    registry = request.app.state.metrics
    # Bug #5 fix: sync guardrail_trigger_count từ GuardrailRunner vào MetricsRegistry
    container = getattr(request.app.state, "container", None)
    if container is not None:
        guardrails = getattr(container, "guardrails", None)
        if guardrails is not None:
            registry.guardrail_trigger_count = getattr(guardrails, "trigger_count", 0)
    return PlainTextResponse(registry.render_prometheus())
