"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import __version__
from app.agent.fake_llm import DemoLLM
from app.agent.loop import AgentConfig
from app.agent.openai_client import OpenAIChatClient, make_openai_embedder
from app.api.routes import build_router
from app.checks.service import CheckService, LLMFactory
from app.config import LLMMode, Settings, get_settings
from app.datasheets.registry import DatasheetRegistry
from app.logging_utils import configure_logging, redact, register_secrets

log = logging.getLogger("speccheck")


def default_llm_factory(settings: Settings) -> LLMFactory:
    """Live OpenAI client when a key is configured, otherwise the offline demo."""

    def factory(requirements, datasheet):
        if settings.llm_mode is LLMMode.LIVE:
            assert settings.openai_api_key is not None
            return OpenAIChatClient(
                settings.openai_api_key.get_secret_value(),
                settings.openai_model,
                timeout=settings.openai_timeout_seconds,
            )
        return DemoLLM(requirements, datasheet.is_sample, delay=settings.demo_delay_seconds)

    return factory


def create_app(settings: Settings | None = None, llm_factory: LLMFactory | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    register_secrets(settings.secret_values)

    embedder = None
    if settings.use_embeddings and settings.llm_mode is LLMMode.LIVE:
        assert settings.openai_api_key is not None
        embedder = make_openai_embedder(settings.openai_api_key.get_secret_value())

    registry = DatasheetRegistry(
        ttl_seconds=settings.datasheet_ttl_seconds,
        max_bytes=settings.max_upload_mb * 1024 * 1024,
        max_pages=settings.max_pdf_pages,
        embedder=embedder,
    )
    service = CheckService(
        registry,
        llm_factory or default_llm_factory(settings),
        mode=settings.llm_mode.value,
        agent_config=AgentConfig(
            max_steps=settings.agent_max_steps,
            max_tokens=settings.agent_max_tokens,
            timeout_seconds=settings.agent_timeout_seconds,
            max_pages_read=settings.agent_max_pages_read,
        ),
        min_confidence=settings.min_confidence,
        ttl_seconds=settings.check_ttl_seconds,
        max_concurrent_runs=settings.max_concurrent_runs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        registry.sample()  # parse the built-in sample once at startup
        if settings.llm_mode is LLMMode.OFFLINE:
            log.warning(
                "OPENAI_API_KEY is not set: running in OFFLINE DEMO mode. "
                "Create a .env file (see .env.example) to enable the live LLM agent."
            )
        else:
            log.info("Live LLM mode with model %s", settings.openai_model)
        yield
        await service.wait_all()

    app = FastAPI(
        title="SpecCheck API",
        version=__version__,
        description="Verifies hardware requirements against component datasheets.",
        lifespan=lifespan,
    )
    limiter = Limiter(key_func=get_remote_address, headers_enabled=False)
    app.state.limiter = limiter
    app.state.settings = settings
    app.state.registry = registry
    app.state.service = service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            {"detail": f"Rate limit exceeded ({exc.detail}). Please slow down."}, status_code=429
        )

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": list(e.get("loc", [])),
                "msg": redact(str(e.get("msg", ""))).removeprefix("Value error, "),
            }
            for e in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    app.include_router(build_router(settings, limiter, registry, service))
    return app
