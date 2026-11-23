import pytest
import os
from contextlib import contextmanager
from fastapi import HTTPException, Request
from pydantic import ValidationError

from woori_youtube.api import ContentSettingsUpdate, _require_local_write


def request(client, origin=None):
    headers = [(b"host", b"127.0.0.1:8000")]
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "method": "PUT", "path": "/", "headers": headers,
                    "client": (client, 1234), "server": ("127.0.0.1", 8000), "scheme": "http"})


def test_settings_reject_cross_origin_remote_and_invalid_goals():
    _require_local_write(request("127.0.0.1", "http://127.0.0.1:8000"))
    with pytest.raises(HTTPException):
        _require_local_write(request("127.0.0.1", "https://untrusted.example"))
    with pytest.raises(HTTPException):
        _require_local_write(request("192.0.2.1"))
    with pytest.raises(ValidationError):
        ContentSettingsUpdate(daily_goal=-1, enabled=True)
    assert ContentSettingsUpdate(daily_goal=20, enabled=True).daily_goal == 20


def test_dashboard_escapes_job_errors(monkeypatch):
    from woori_youtube import api
    class Store:
        def list_jobs(self, limit):
            return [{"channel_id": "us", "job_date": "2026-11-23", "status": "failed",
                     "attempts": 0, "error": "<script>alert(1)</script>"}]
    monkeypatch.setattr(api.app.state, "store", Store(), raising=False)
    html = api.dashboard()
    assert "&lt;script&gt;" in html and "<script>alert(1)</script>" not in html


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_settings_write_and_read_with_postgres(monkeypatch):
    import sqlalchemy
    from woori_youtube import api
    from woori_youtube.content_types import ContentType
    real_engine = sqlalchemy.create_engine(os.environ["TEST_POSTGRES_URL"])
    with real_engine.connect() as conn:
        transaction = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
            @contextmanager
            def connect(self): yield conn
            def dispose(self): pass
        monkeypatch.setattr(sqlalchemy, "create_engine", lambda *args, **kwargs: TransactionEngine())
        try:
            result = api.update_content_type(ContentType.SINGLE_SHORT,
                ContentSettingsUpdate(daily_goal=20, enabled=False), request("127.0.0.1"), channel="us-economy")
            assert result["daily_goal"] == 20 and result["enabled"] is False
            short = next(row for row in api.content_types("us-economy") if row["content_type"] == "SINGLE_SHORT")
            assert short["daily_goal"] == 20 and not short["enabled"]
        finally:
            transaction.rollback()
    real_engine.dispose()
