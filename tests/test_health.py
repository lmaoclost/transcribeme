"""Lock in /health deep-check contract: status + db + redis keys, degraded on failure."""

from __future__ import annotations


def test_health_reports_all_checks(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert "db" in payload
    assert "redis" in payload


def test_health_degraded_when_db_down(client, monkeypatch):
    import app.db

    def boom(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(app.db, "SessionLocal", boom)

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["db"].startswith("error:")


def test_health_degraded_when_redis_down(client, monkeypatch):
    import redis

    def boom(*args, **kwargs):
        raise RuntimeError("redis gone")

    monkeypatch.setattr(redis, "from_url", boom)

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["redis"].startswith("error:")
