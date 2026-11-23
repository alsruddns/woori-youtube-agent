from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .channels import load_channels
from .config import settings
from .store import JobStore


def get_store():
    url = settings.database_url
    if url.startswith("postgresql"):
        from .postgres_store import PostgresJobStore
        store = PostgresJobStore(url)
        store.initialize()
        return store
    path = Path(url.removeprefix("sqlite:///"))
    return JobStore(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = get_store()
    app.state.store.recover_interrupted()
    yield


app = FastAPI(title="Woori YouTube Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "codex_enabled": settings.codex_enabled, "youtube_enabled": settings.youtube_enabled}


@app.get("/api/channels")
def channels():
    catalog = load_channels(settings.channels_file)
    return [{"channel_id": c.channel_id, "locale": c.locale, "country": c.country, "categories": c.categories, "enabled": c.enabled}
            for c in catalog.values()]


@app.get("/api/jobs")
def jobs(limit: int = 50):
    return app.state.store.list_jobs(max(1, min(limit, 200)))


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    result = app.state.store.get_job(job_id)
    if result is None:
        raise HTTPException(404, "Job not found")
    return result


@app.get("/", response_class=HTMLResponse)
def dashboard():
    rows = app.state.store.list_jobs(30)
    table = "".join(f"<tr><td>{r['channel_id']}</td><td>{r['job_date']}</td><td>{r['status']}</td><td>{r.get('attempts', 0)}</td><td>{r.get('error') or ''}</td></tr>" for r in rows)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Woori YouTube Agent</title>
    <style>body{{font:15px system-ui;margin:3rem;background:#101827;color:#e5e7eb}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.7rem;border-bottom:1px solid #334155;text-align:left}}.pill{{color:#7dd3fc}}</style></head>
    <body><h1>Woori YouTube Agent</h1><p class='pill'>Local operations dashboard · {len(rows)} recent jobs</p><table><thead><tr><th>Channel</th><th>Date</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead><tbody>{table}</tbody></table></body></html>"""
