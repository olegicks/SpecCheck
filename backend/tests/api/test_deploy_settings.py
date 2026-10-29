"""Production hardening: CORS for preview deployments, proxy-aware rate limits."""

import httpx

from tests.api.conftest import make_settings

VERCEL_REGEX = r"^https://speccheck(-[a-z0-9-]+)?\.vercel\.app$"


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


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
