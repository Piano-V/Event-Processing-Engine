import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_ingest_event_unauthorized(client: AsyncClient):
    """
    Test that ingesting an event without a JWT token fails with HTTP 401.
    """
    response = await client.post(
        "/api/v1/events/ingest",
        json={"event_type": "user.signup", "payload": {}}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_ingest_event_success(client: AsyncClient):
    """
    Test successful event ingestion with a valid auth token.
    """
    # Register & Authenticate User
    await client.post(
        "/api/v1/auth/register",
        json={"username": "eventuser", "password": "password123"}
    )
    token_resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "eventuser", "password": "password123"}
    )
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest event
    response = await client.post(
        "/api/v1/events/ingest",
        json={"event_type": "user.signup", "payload": {"plan": "pro"}},
        headers=headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["event_type"] == "user.signup"
    assert data["payload"]["plan"] == "pro"
    assert "id" in data
    assert "timestamp" in data

@pytest.mark.asyncio
async def test_get_analytics_summary(client: AsyncClient):
    """
    Test retrieval of analytics counters.
    """
    # Authenticate User
    token_resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "eventuser", "password": "password123"}
    )
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest another event
    await client.post(
        "/api/v1/events/ingest",
        json={"event_type": "payment.processed", "payload": {"value": 50.0}},
        headers=headers
    )

    # Get analytics summary
    response = await client.get("/api/v1/events/analytics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_events" in data
    assert data["total_events"] >= 2
    assert "payment.processed" in data["event_types"]
    assert "cached_at" in data
