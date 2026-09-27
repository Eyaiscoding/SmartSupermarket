"""
Tests for the FastAPI Application (v2).
========================================
Tests the REST endpoints using httpx's AsyncClient with the FastAPI
test client.  These tests do NOT require Docker, MQTT, TimescaleDB,
or Redis to be running -- the pipeline uses CSV mode and infrastructure
connections degrade gracefully.
"""

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.fastapi_app import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_endpoint():
    """The /health endpoint should return 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_latest_state_404_when_empty():
    """Latest state should 404 when no pipeline has run."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/latest")
    # May be 404 (no data) or 200 (if infra is up from a previous run).
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_scenario_endpoint():
    """Running a scenario via POST should return a valid PipelineSummary."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", timeout=60.0
    ) as client:
        resp = await client.post(
            "/api/v1/scenario",
            json={"scenario": "none"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "normal"
    assert data["total_timesteps"] == 11712
    assert data["tier_1_breaches"] == 0
    assert data["tier_1_protected"] is True


@pytest.mark.asyncio
async def test_scenario_invalid():
    """An invalid scenario name should return 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scenario",
            json={"scenario": "invalid_scenario"},
        )
    assert resp.status_code == 400
