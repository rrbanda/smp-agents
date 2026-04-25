"""Health check endpoints for Kubernetes liveness/readiness probes."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared.neo4j_tools import _neo4j_http_query

logger = logging.getLogger(__name__)


async def healthz(request: Request) -> JSONResponse:
    """Liveness probe -- confirms the process is running."""
    return JSONResponse({"status": "ok"})


async def readyz(request: Request) -> JSONResponse:
    """Readiness probe -- checks Neo4j connectivity."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        _neo4j_http_query("RETURN 1 AS ping")
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"
        healthy = False
        logger.warning("Readiness check: Neo4j unreachable: %s", e)

    status_code = 200 if healthy else 503
    return JSONResponse({"status": "ready" if healthy else "not_ready", "checks": checks}, status_code=status_code)


health_routes = [
    Route("/healthz", healthz),
    Route("/readyz", readyz),
]
