"""Health check endpoints for Kubernetes liveness/readiness probes."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


async def healthz(request: Request) -> JSONResponse:
    """Liveness probe -- confirms the process is running."""
    return JSONResponse({"status": "ok"})


async def readyz(request: Request) -> JSONResponse:
    """Readiness probe -- the agent process is ready to accept traffic.

    Neo4j is treated as a soft dependency: if unreachable the agent still
    reports ready (degraded) so that non-graph endpoints remain accessible.
    """
    checks: dict[str, str] = {}

    try:
        from shared.neo4j_tools import _neo4j_http_query

        _neo4j_http_query("RETURN 1 AS ping")
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"degraded: {e}"
        logger.warning("Readiness check: Neo4j unreachable (degraded): %s", e)

    return JSONResponse({"status": "ready", "checks": checks}, status_code=200)


health_routes = [
    Route("/healthz", healthz),
    Route("/readyz", readyz),
]
