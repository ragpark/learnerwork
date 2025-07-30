import os
import importlib.util
from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.fixture(scope="session")
def app():
    """Load the FastAPI app from main.py."""
    os.environ.setdefault("API_TOKEN", "dev-token-123")
    spec = importlib.util.spec_from_file_location(
        "main", Path(__file__).resolve().parents[1] / "lms-content-push" / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "healthy"


@pytest.mark.asyncio
async def test_destinations(app):
    headers = {"Authorization": "Bearer dev-token-123"}
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/destinations", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "main_lrs" in data
    assert "analytics_webhook" in data

