"""Production hardening: access code, CORS for preview deployments, proxy-aware rate limits."""

import logging

import httpx

from tests.api.conftest import make_settings, run_check
from tests.conftest import make_pdf

TOKEN = "demo-access-code-1234"
VERCEL_REGEX = r"^https://speccheck(-[a-z0-9-]+)?\.vercel\.app$"


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_access_code_protects_costly_endpoints(app_factory, template_requirements) -> None:
    app = app_factory(make_settings(SPECCHECK_ACCESS_TOKEN=TOKEN))
    body = {"datasheet_id": "sc-mcu-100", "requirements": template_requirements[:1]}
    pdf = make_pdf(["<p>hello world</p>"])
    async with client_for(app) as c:
        assert (await c.get("/health")).json()["auth_required"] is True
        # missing / wrong code
        assert (await c.post("/api/checks", json=body)).status_code == 401
        wrong = await c.post("/api/checks", json=body, headers={"X-Access-Token": "nope"})
        assert wrong.status_code == 401
        assert "access code" in wrong.json()["detail"]
        upload = await c.post("/api/datasheets", files={"file": ("x.pdf", pdf)})
        assert upload.status_code == 401
        # read-only endpoints stay public
        assert (await c.get("/api/samples")).status_code == 200
        assert (await c.get("/api/templates")).status_code == 200
        # correct code
        c.headers["X-Access-Token"] = TOKEN
        upload = await c.post("/api/datasheets", files={"file": ("x.pdf", pdf)})
        assert upload.status_code == 201
        check_id = await run_check(c, template_requirements[:1])
        assert (await c.get(f"/api/checks/{check_id}")).json()["state"] == "completed"


async def test_no_access_code_by_default(client) -> None:
    assert (await client.get("/health")).json()["auth_required"] is False


async def test_access_code_is_redacted_from_logs(app_factory, caplog) -> None:
    app_factory(make_settings(SPECCHECK_ACCESS_TOKEN=TOKEN))
    logging.getLogger("speccheck.test").warning("token=%s", TOKEN)
    assert TOKEN not in caplog.text


async def test_cors_allows_vercel_previews_by_regex(app_factory) -> None:
    app = app_factory(
        make_settings(
            SPECCHECK_CORS_ORIGINS="https://speccheck.vercel.app",
            SPECCHECK_CORS_ORIGIN_REGEX=VERCEL_REGEX,
        )
    )
    async with client_for(app) as c:
        for origin, allowed in (
            ("https://speccheck.vercel.app", True),
            ("https://speccheck-git-feature-x-olegicks.vercel.app", True),
            ("https://evil.example.com", False),
            ("https://speccheck.vercel.app.evil.com", False),
        ):
            r = await c.get("/health", headers={"Origin": origin})
            assert (r.headers.get("access-control-allow-origin") == origin) is allowed, origin


async def test_rate_limit_is_per_client_ip(app_factory, template_requirements) -> None:
    """Behind a proxy (with --forwarded-allow-ips) each client gets its own budget."""
    app = app_factory(make_settings(SPECCHECK_RATE_LIMIT_CHECKS="1/minute"))
    body = {"datasheet_id": "sc-mcu-100", "requirements": template_requirements[:1]}
    a = httpx.ASGITransport(app=app, client=("203.0.113.1", 1234))
    b = httpx.ASGITransport(app=app, client=("203.0.113.2", 1234))
    async with (
        httpx.AsyncClient(transport=a, base_url="http://t") as ca,
        httpx.AsyncClient(transport=b, base_url="http://t") as cb,
    ):
        assert (await ca.post("/api/checks", json=body)).status_code == 202
        assert (await ca.post("/api/checks", json=body)).status_code == 429
        assert (await cb.post("/api/checks", json=body)).status_code == 202
        await app.state.service.wait_all()


def test_dockerfile_trusts_proxy_and_uses_platform_port() -> None:
    from pathlib import Path

    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(encoding="utf-8")
    assert "--proxy-headers" in dockerfile and "--forwarded-allow-ips" in dockerfile
    assert "${PORT:-8000}" in dockerfile and 'os.environ.get(\\"PORT\\"' in dockerfile
