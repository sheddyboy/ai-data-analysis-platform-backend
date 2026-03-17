"""Tests for dataset endpoints — upload, list, metadata, delete, and ownership."""

import io
import pytest
from httpx import AsyncClient


def _csv_file(content: str = "name,age\nAlice,30\nBob,25") -> dict:
    return {"file": ("test.csv", io.BytesIO(content.encode()), "text/csv")}


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/datasets/upload", files=_csv_file())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_and_list(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/datasets/upload", headers=auth_headers, files=_csv_file())
    assert resp.status_code == 201
    data = resp.json()
    assert "dataset_id" in data
    assert data["status"] == "ready"

    list_resp = await client.get("/api/v1/datasets", headers=auth_headers)
    assert list_resp.status_code == 200
    ids = [d["dataset_id"] for d in list_resp.json()["datasets"]]
    assert data["dataset_id"] in ids


@pytest.mark.asyncio
async def test_list_scoped_to_user(client: AsyncClient, auth_headers: dict):
    """A second user should not see the first user's datasets."""
    # Register second user
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "pass5678"})
    resp2 = await client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "pass5678"})
    other_headers = {"Authorization": f"Bearer {resp2.json()['access_token']}"}

    # Upload under first user
    up = await client.post("/api/v1/datasets/upload", headers=auth_headers, files=_csv_file())
    dataset_id = up.json()["dataset_id"]

    # Second user's list should not contain it
    list_resp = await client.get("/api/v1/datasets", headers=other_headers)
    ids = [d["dataset_id"] for d in list_resp.json()["datasets"]]
    assert dataset_id not in ids


@pytest.mark.asyncio
async def test_get_metadata_ownership(client: AsyncClient, auth_headers: dict):
    """A different user cannot fetch another user's dataset metadata."""
    up = await client.post("/api/v1/datasets/upload", headers=auth_headers, files=_csv_file())
    dataset_id = up.json()["dataset_id"]

    await client.post("/api/v1/auth/register", json={"email": "intruder@example.com", "password": "pass5678"})
    resp2 = await client.post("/api/v1/auth/login", json={"email": "intruder@example.com", "password": "pass5678"})
    intruder = {"Authorization": f"Bearer {resp2.json()['access_token']}"}

    resp = await client.get(f"/api/v1/datasets/{dataset_id}/metadata", headers=intruder)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_dataset(client: AsyncClient, auth_headers: dict):
    up = await client.post("/api/v1/datasets/upload", headers=auth_headers, files=_csv_file())
    dataset_id = up.json()["dataset_id"]

    del_resp = await client.delete(f"/api/v1/datasets/{dataset_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    meta_resp = await client.get(f"/api/v1/datasets/{dataset_id}/metadata", headers=auth_headers)
    assert meta_resp.status_code == 404
