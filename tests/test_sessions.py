"""Tests for session CRUD and ownership scoping."""

import io
import pytest
from httpx import AsyncClient


def _csv_file():
    return {"file": ("data.csv", io.BytesIO(b"col1,col2\n1,2\n3,4"), "text/csv")}


async def _upload(client, headers):
    resp = await client.post("/api/v1/datasets/upload", headers=headers, files=_csv_file())
    return resp.json()["dataset_id"]


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient, auth_headers: dict):
    dataset_id = await _upload(client, auth_headers)
    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/sessions",
        headers=auth_headers,
        json={"title": "My session"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My session"
    assert data["dataset_id"] == dataset_id


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient, auth_headers: dict):
    dataset_id = await _upload(client, auth_headers)
    await client.post(f"/api/v1/datasets/{dataset_id}/sessions", headers=auth_headers, json={})
    await client.post(f"/api/v1/datasets/{dataset_id}/sessions", headers=auth_headers, json={})

    resp = await client.get(f"/api/v1/datasets/{dataset_id}/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_session_ownership(client: AsyncClient, auth_headers: dict):
    """Another user cannot access a session they don't own."""
    dataset_id = await _upload(client, auth_headers)
    sess = await client.post(
        f"/api/v1/datasets/{dataset_id}/sessions", headers=auth_headers, json={}
    )
    session_id = sess.json()["session_id"]

    await client.post("/api/v1/auth/register", json={"email": "sess_intruder@example.com", "password": "pass5678"})
    r = await client.post("/api/v1/auth/login", json={"email": "sess_intruder@example.com", "password": "pass5678"})
    intruder = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.get(f"/api/v1/sessions/{session_id}", headers=intruder)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient, auth_headers: dict):
    dataset_id = await _upload(client, auth_headers)
    sess = await client.post(
        f"/api/v1/datasets/{dataset_id}/sessions", headers=auth_headers, json={}
    )
    session_id = sess.json()["session_id"]

    del_resp = await client.delete(f"/api/v1/sessions/{session_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert "checks" in resp.json()
