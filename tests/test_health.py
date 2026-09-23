"""Lock in /health deep-check contract: status + db + redis + workers + queues + disk + dirs."""


def test_health_reports_all_checks(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    for key in ("db", "redis", "workers", "queues", "disk", "dirs"):
        assert key in payload


def test_health_degraded_when_db_down(client, monkeypatch):
    import app.db

    def boom(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(app.db, "SessionLocal", boom)

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["db"]["error"] == "db gone"


def test_health_degraded_when_redis_down(client, monkeypatch):
    import redis

    def boom(*args, **kwargs):
        raise RuntimeError("redis gone")

    monkeypatch.setattr(redis, "from_url", boom)

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["redis"]["error"] == "redis gone"


def test_health_degraded_when_fewer_than_two_workers(client, monkeypatch):
    from app.routers import health as health_router

    monkeypatch.setattr(
        health_router,
        "_check_workers",
        lambda: {"status": "ok", "workers": ["celery@only-one"]},
    )

    payload = client.get("/health").json()
    assert payload["workers"]["workers"] == ["celery@only-one"]


def test_health_degraded_on_low_disk(client, monkeypatch):
    from app.routers import health as health_router

    monkeypatch.setattr(
        health_router, "_check_disk", lambda: {"status": "degraded", "free_gb": 0.5}
    )

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["disk"]["free_gb"] == 0.5


def test_health_degraded_when_dirs_missing(client, monkeypatch):
    from app.routers import health as health_router

    monkeypatch.setattr(
        health_router,
        "_check_dirs",
        lambda: {"status": "degraded", "missing": ["models"]},
    )

    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["dirs"]["missing"] == ["models"]
