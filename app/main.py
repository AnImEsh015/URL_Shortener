"""Main FastAPI application factory, middleware, router registration, and health checks.

Configures:
- Correlation / Request-ID tracking middleware (X-Request-ID)
- CORS middleware
- Health check endpoint (/health) verifying PostgreSQL and Redis
- Router mounting (Redirect router mounted LAST to prevent route shadowing)
"""

import contextvars
import logging
import uuid

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.services.cache import get_redis_client

# Context variable for correlation ID across synchronous calls
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request ID into log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True


# Configure root logging format
handler = logging.StreamHandler()
handler.addFilter(RequestIdFilter())
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [req:%(request_id)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
logger = logging.getLogger("app.main")


def create_app() -> FastAPI:
    """Application factory building and configuring the FastAPI app."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Request ID Middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        # Extract existing X-Request-ID or generate new UUID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        logger.info(f"Incoming request {request.method} {request.url.path}")
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            logger.info(f"Finished request {request.method} {request.url.path}")
            request_id_ctx.reset(token)

    # 3. Health Check Endpoint
    @app.get(
        "/health",
        tags=["Health"],
        summary="Service Health Check",
        response_model=dict[str, str],
    )
    def health_check():
        """Checks both PostgreSQL and Redis connectivity.

        Returns 200 OK if both components respond, or 503 Service Unavailable
        if either dependency fails.
        """
        db_healthy = False
        redis_healthy = False

        # Verify PostgreSQL database
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_healthy = True
        except Exception as e:
            logger.error(f"Health check DB error: {e}")
            db_healthy = False
        finally:
            db.close()

        # Verify Redis cache
        try:
            r = get_redis_client()
            if r.ping():
                redis_healthy = True
        except Exception as e:
            logger.error(f"Health check Redis error: {e}")
            redis_healthy = False

        status_code = (
            status.HTTP_200_OK
            if (db_healthy and redis_healthy)
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ok" if (db_healthy and redis_healthy) else "unhealthy",
                "database": "ok" if db_healthy else "down",
                "redis": "ok" if redis_healthy else "down",
            },
        )

    # Import and register routers
    from app.routers import auth, links, redirect, stats

    app.include_router(auth.router, prefix="/auth", tags=["Auth"])
    app.include_router(links.router, prefix="/api/links", tags=["Links"])
    app.include_router(stats.router, prefix="/api/links", tags=["Stats"])

    # Redirect router MUST be registered LAST to avoid shadowing other endpoints
    app.include_router(redirect.router, tags=["Redirect"])

    return app


app = create_app()
