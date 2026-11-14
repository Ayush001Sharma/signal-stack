"""FastAPI application entrypoint."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import briefs, companies, ops, signals, sources
from app.api.deps import require_api_key
from app.core.config import get_settings
from app.core.db import engine
from app.core.logging import configure_logging
from app.services.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("signalstack")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    log.info("Signal Stack API started")
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Signal Stack API",
    version="1.0.0",
    description="Company Intelligence & Executive Briefing Engine — research, adaptive interview, source discovery, monitoring, explainable ranking and Monday Morning Briefs.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        log.info(f"{request.method} {request.url.path} {response.status_code}", extra={"duration_ms": int((time.time() - t0) * 1000)})
    return response


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Conflict with existing data", "error": str(exc.orig)[:300]})


@app.exception_handler(SQLAlchemyError)
async def db_handler(request: Request, exc: SQLAlchemyError):
    log.exception("database error")
    return JSONResponse(status_code=500, content={"detail": "Database error"})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "type": type(exc).__name__})


for r in (companies.router, sources.router, signals.router, briefs.router, ops.router):
    app.include_router(r, prefix="/api", dependencies=[Depends(require_api_key)])


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except SQLAlchemyError:
        db_ok = False
    from app.services.scheduler import get_scheduler

    sch = get_scheduler()
    status = "ok" if db_ok else "degraded"
    return JSONResponse(status_code=200 if db_ok else 503, content={"status": status, "database": db_ok, "scheduler": bool(sch and sch.running) or not settings.scheduler_enabled})
