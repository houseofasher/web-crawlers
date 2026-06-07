from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from omnispider.core.config import load_config
from omnispider.core.models import (
    CrawlJobSpec,
    ErrorEnvelope,
    JobCreateRequest,
    JobResponse,
    PageRecord,
)
from omnispider.core.orchestrator import Orchestrator
from omnispider.security.audit_log import AuditEventType
from omnispider.security.middleware import NomadSecurityMiddleware
from omnispider.security.nomad_stack import NomadSecurityStack, build_security_stack

log = structlog.get_logger()
_cfg = load_config()
_orchestrator: Orchestrator | None = None
_security: NomadSecurityStack | None = None
_pulse_task: asyncio.Task | None = None

if _cfg.security.enabled:
    _security = build_security_stack(_cfg)


async def _organism_pulse_loop() -> None:
    interval = _cfg.security.organism_pulse_seconds
    while True:
        await asyncio.sleep(interval)
        if _security:
            _security.vital_guard.pulse()
            if not _security.vital_guard.is_vital():
                _security.audit.record(
                    AuditEventType.AUDIT_CHAIN_BREACH,
                    detail="organism lockdown after pulse",
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _pulse_task
    _orchestrator = Orchestrator(_cfg, security=_security)
    await _orchestrator.initialize()
    if _cfg.security.enabled and _security:
        _pulse_task = asyncio.create_task(_organism_pulse_loop())
    log.info("api_started", security_enabled=_cfg.security.enabled, dev_mode=_cfg.security.dev_mode)
    yield
    if _pulse_task:
        _pulse_task.cancel()
    if _orchestrator:
        await _orchestrator.shutdown()
    log.info("api_stopped")


app = FastAPI(
    title="Omnispider API",
    version="0.2.0",
    description="Unified web spider orchestrator with Nomad Cyber security perimeter",
    lifespan=lifespan,
)

if _security:
    app.add_middleware(
        NomadSecurityMiddleware,
        audit=_security.audit,
        rbac=_security.rbac,
        auth=_security.auth,
        allowlist=_security.allowlist,
        rate_limiter=_security.rate_limiter,
        distributed=_security.distributed,
        replay_guard=_security.replay_guard,
        vital_guard=_security.vital_guard,
        max_body_bytes=_cfg.security.max_body_bytes,
        dev_mode=_cfg.security.dev_mode,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", None) or request.headers.get(
        "X-Correlation-ID", str(uuid.uuid4())
    )
    envelope = ErrorEnvelope(
        error=str(exc.detail),
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())


def _orch() -> Orchestrator:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


def _sec() -> NomadSecurityStack:
    if _security is None:
        raise HTTPException(status_code=503, detail="Security stack not initialized")
    return _security


def _job_response(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        pages_failed=job.pages_failed,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
    )


@app.get("/health")
async def health() -> dict:
    vital = _security.vital_guard.is_vital() if _security else True
    return {
        "status": "ok" if vital else "degraded",
        "service": "omnispider",
        "version": "0.2.0",
        "security": "nomad_cyber",
        "organism_vital": vital,
    }


@app.get("/organism/vitals")
async def organism_vitals() -> dict:
    report = _sec().vital_guard.get_vitals_report()
    return report.model_dump()


@app.get("/v1/audit")
async def audit_log(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> dict:
    events = _sec().audit.query(limit)
    valid, errors = _sec().audit.verify_chain()
    return {
        "chain_valid": valid,
        "chain_errors": errors,
        "events": [e.model_dump() for e in events],
    }


@app.post("/v1/jobs", response_model=JobResponse, status_code=202)
async def create_job(body: JobCreateRequest, request: Request) -> JobResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        spec = CrawlJobSpec(
            seeds=[str(s) for s in body.seeds],
            engine=body.engine,
            max_depth=body.max_depth,
            max_pages=body.max_pages,
            include_archive=body.include_archive,
            include_sitemaps=body.include_sitemaps,
            js_rendering=body.js_rendering,
            allowed_domains=body.allowed_domains,
        )
        job = await _orch().submit_job(spec, correlation_id=correlation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _job_response(job)


@app.get("/v1/jobs", response_model=list[JobResponse])
async def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[JobResponse]:
    jobs = await _orch().list_jobs(limit)
    return [_job_response(j) for j in jobs]


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = await _orch().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@app.get("/v1/jobs/{job_id}/pages", response_model=list[PageRecord])
async def get_job_pages(
    job_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PageRecord]:
    job = await _orch().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return await _orch().list_pages(job_id, limit, offset)


@app.get("/v1/engines")
async def list_engines() -> dict:
    return {
        "engines": [
            {"id": "http", "description": "Native async HTTP crawler"},
            {"id": "playwright", "description": "JavaScript rendering via Playwright"},
            {"id": "archive", "description": "Internet Archive Wayback Machine"},
            {"id": "katana", "description": "Fast Go-based link discovery"},
            {"id": "splash", "description": "Splash JS render sidecar"},
            {"id": "mechanical", "description": "MechanicalSoup form crawler"},
            {"id": "scrapy", "description": "Scrapy batch spider adapter"},
            {"id": "auto", "description": "Automatic engine routing"},
        ],
        "security": {
            "stack": "nomad_cyber",
            "features": [
                "rbac",
                "audit_chain",
                "replay_guard",
                "ssrf_protection",
                "rate_limiting",
                "organism_vital_guard",
            ],
        },
        "vendors_path": _cfg.vendors.path,
    }
