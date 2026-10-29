"""HTTP routes. Built inside a factory so limits and services come from settings."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter

from app import __version__
from app.checks.export import MEDIA_TYPES, ExportFormat, export
from app.checks.models import CheckRequest, CheckRun, OverrideRequest, RequirementResult, RunState
from app.checks.service import CheckNotFound, CheckService, TooManyRuns
from app.config import Settings
from app.core.requirements import Requirement
from app.core.requirements_io import (
    RequirementsImportError,
    parse_csv,
    parse_yaml,
    to_csv,
    to_yaml,
)
from app.core.templates import TEMPLATES, get_template
from app.datasheets.pdf import DatasheetError, render_page_png
from app.datasheets.registry import DatasheetRegistry


class ImportRequest(BaseModel):
    format: Literal["yaml", "csv"]
    content: str = Field(max_length=200_000)


class ExportRequirementsRequest(BaseModel):
    format: Literal["yaml", "csv"]
    requirements: list[Requirement] = Field(max_length=200)


def _unknown_requirement(requirement_id: str) -> HTTPException:
    return HTTPException(404, f"Requirement {requirement_id} is not part of this check.")


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event}\ndata: {data}\n\n"


def build_router(
    settings: Settings, limiter: Limiter, registry: DatasheetRegistry, service: CheckService
) -> APIRouter:
    router = APIRouter()
    max_bytes = settings.max_upload_mb * 1024 * 1024

    def get_run(check_id: str) -> CheckRun:
        try:
            return service.get(check_id)
        except CheckNotFound:
            raise HTTPException(404, "Check not found (it may have expired).") from None

    # -- meta ------------------------------------------------------------------------

    @router.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "mode": settings.llm_mode.value,
            "model": settings.openai_model if settings.llm_mode.value == "live" else "offline-demo",
        }

    @router.get("/api/templates")
    async def templates() -> list[dict]:
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "requirements": [r.model_dump(mode="json") for r in get_template(tid)],
            }
            for tid, t in TEMPLATES.items()
        ]

    # -- requirements import/export ------------------------------------------------------

    @router.post("/api/requirements/import")
    async def import_requirements(body: ImportRequest) -> list[Requirement]:
        try:
            return parse_yaml(body.content) if body.format == "yaml" else parse_csv(body.content)
        except RequirementsImportError as exc:
            raise HTTPException(422, {"errors": exc.errors}) from None

    @router.post("/api/requirements/export")
    async def export_requirements(body: ExportRequirementsRequest) -> Response:
        if body.format == "yaml":
            return Response(to_yaml(body.requirements), media_type="application/x-yaml")
        return Response(to_csv(body.requirements), media_type="text/csv; charset=utf-8")

    # -- datasheets ------------------------------------------------------------------------

    @router.get("/api/samples")
    async def samples() -> list[dict]:
        sheet = registry.sample()
        return [
            sheet.summary()
            | {
                "description": "Fictional 32-bit automotive MCU datasheet with deliberate "
                "edge cases (tables, mV units, footnotes, variant-dependent values)."
            }
        ]

    @router.post("/api/datasheets", status_code=status.HTTP_201_CREATED)
    @limiter.limit(lambda: settings.rate_limit_uploads)
    async def upload_datasheet(request: Request, file: Annotated[UploadFile, File()]) -> dict:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes + 64 * 1024:
            raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
        try:
            sheet = registry.add_upload(data, file.filename or "upload.pdf")
        except DatasheetError as exc:
            raise HTTPException(422, str(exc)) from None
        return sheet.summary()

    @router.get("/api/datasheets/{datasheet_id}")
    async def datasheet(datasheet_id: str) -> dict:
        sheet = registry.get(datasheet_id)
        if sheet is None:
            raise HTTPException(404, "Datasheet not found (uploads expire after 30 minutes).")
        return sheet.summary()

    @router.get("/api/datasheets/{datasheet_id}/pages/{page}.png")
    @limiter.limit("120/minute")
    async def page_png(
        request: Request,
        datasheet_id: str,
        page: int,
        highlight: Annotated[str | None, Query(max_length=600)] = None,
    ) -> Response:
        sheet = registry.get(datasheet_id)
        if sheet is None:
            raise HTTPException(404, "Datasheet not found.")
        try:
            png = render_page_png(sheet.data, page, highlight)
        except DatasheetError as exc:
            raise HTTPException(404, str(exc)) from None
        return Response(
            png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"}
        )

    # -- checks ------------------------------------------------------------------------------

    @router.post("/api/checks", status_code=status.HTTP_202_ACCEPTED)
    @limiter.limit(lambda: settings.rate_limit_checks)
    async def start_check(request: Request, body: CheckRequest) -> CheckRun:
        ids = [r.id for r in body.requirements]
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Requirement ids must be unique.")
        sheet = registry.get(body.datasheet_id)
        if sheet is None:
            raise HTTPException(404, "Datasheet not found (uploads expire after 30 minutes).")
        try:
            return service.start(sheet, body.requirements)
        except TooManyRuns as exc:
            raise HTTPException(429, str(exc)) from None

    @router.get("/api/checks/{check_id}")
    async def get_check(check_id: str) -> CheckRun:
        return get_run(check_id)

    @router.get("/api/checks/{check_id}/events")
    async def check_events(request: Request, check_id: str) -> StreamingResponse:
        get_run(check_id)
        bus = service.bus(check_id)
        last = request.headers.get("last-event-id", "0")
        after = int(last) if last.isdigit() else 0

        async def stream():
            yield "retry: 3000\n\n"
            async for event in bus.subscribe(after_seq=after):
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse("agent", event.model_dump_json(), event.seq)
                if await request.is_disconnected():
                    return
            run = service.get(check_id)
            yield _sse("done", json.dumps({"state": run.state.value, "id": run.id}))

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.patch("/api/checks/{check_id}/findings/{requirement_id}")
    async def override_finding(
        check_id: str, requirement_id: str, body: OverrideRequest
    ) -> RequirementResult:
        run = get_run(check_id)
        if run.state is RunState.RUNNING:
            raise HTTPException(409, "The check is still running.")
        try:
            return service.override(check_id, requirement_id, body)
        except CheckNotFound:
            raise HTTPException(
                404, f"Requirement {requirement_id} is not part of this check."
            ) from None

    @router.delete("/api/checks/{check_id}/findings/{requirement_id}/override")
    async def clear_override(check_id: str, requirement_id: str) -> RequirementResult:
        get_run(check_id)
        try:
            return service.clear_override(check_id, requirement_id)
        except CheckNotFound:
            raise HTTPException(
                404, f"Requirement {requirement_id} is not part of this check."
            ) from None

    @router.get("/api/checks/{check_id}/export")
    async def export_check(check_id: str, format: ExportFormat = ExportFormat.MD) -> Response:
        run = get_run(check_id)
        if run.state is RunState.RUNNING:
            raise HTTPException(409, "The check is still running.")
        filename = f"speccheck-{run.id}.{format.value}"
        return Response(
            export(run, format),
            media_type=MEDIA_TYPES[format],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
