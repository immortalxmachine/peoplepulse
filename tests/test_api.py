"""FastAPI endpoint tests via TestClient (mock provider)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from peoplepulse.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_views_lists_only_views():
    r = client.get("/views")
    assert r.status_code == 200
    views = r.json()["allowed_views"]
    assert "v_attrition_overall" in views
    assert "dim_employee" not in views  # base tables never exposed


def test_query_happy_path(warehouse):
    r = client.post("/query", json={"question": "What is the overall attrition rate?"})
    body = r.json()
    assert r.status_code == 200
    assert body["refused"] is False
    assert body["rows"][0][0] > 0


def test_query_refusal(warehouse):
    r = client.post("/query", json={"question": "List all employees by name"})
    body = r.json()
    assert body["refused"] is True
    assert body["reason"] == "individual_data_request"
