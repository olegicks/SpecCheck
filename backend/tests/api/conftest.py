import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.config import Settings, load_settings
from app.core.templates import get_template
from app.main import create_app


def make_settings(**overrides) -> Settings:
    base = {"SPECCHECK_DEMO_DELAY": 0, "SPECCHECK_RATE_LIMIT_CHECKS": "1000/minute"}
    return load_settings(**(base | overrides))


@pytest.fixture
def app_factory() -> Callable:
    return lambda settings=None, llm_factory=None: create_app(
        settings or make_settings(), llm_factory
    )


@pytest.fixture
async def client(app_factory) -> AsyncIterator[httpx.AsyncClient]:
    app = app_factory()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def template_requirements() -> list[dict]:
    return [r.model_dump(mode="json") for r in get_template("vehicle-computer-mcu")]


async def run_check(client: httpx.AsyncClient, requirements: list[dict], datasheet_id="sc-mcu-100"):
    response = await client.post(
        "/api/checks", json={"datasheet_id": datasheet_id, "requirements": requirements}
    )
    assert response.status_code == 202, response.text
    check_id = response.json()["id"]
    for _ in range(500):  # poll like a real client would (max ~5 s)
        if (await client.get(f"/api/checks/{check_id}")).json()["state"] != "running":
            return check_id
        await asyncio.sleep(0.01)
    raise AssertionError("check did not finish")
