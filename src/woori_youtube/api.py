from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from dataclasses import asdict
from html import escape
from ipaddress import ip_address
from urllib.parse import urlparse
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt

from .channels import load_channels
from .config import settings
from .store import JobStore
from .content_types import ContentType, SPECS


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


@app.get("/api/content-types")
def content_types(channel: str = "us-economy"):
    catalog = load_channels(settings.channels_file)
    if channel not in catalog:
        raise HTTPException(404, "Channel not found")
    overrides = {}
    if settings.database_url.startswith("postgresql"):
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                overrides = {row["content_type"]: dict(row) for row in conn.execute(text(
                    "SELECT content_type,enabled,daily_goal FROM content_type_settings WHERE channel_id=:channel"),
                    {"channel": channel}).mappings()}
        finally:
            engine.dispose()
    return [{"content_type": kind.value, **asdict(spec),
             "daily_goal": overrides.get(kind.value, {}).get("daily_goal", spec.daily_goal),
             "enabled": overrides.get(kind.value, {}).get("enabled", True),
             "automatic_production_available": False} for kind, spec in SPECS.items()]


class ContentSettingsUpdate(BaseModel):
    daily_goal: StrictInt = Field(ge=0)
    enabled: StrictBool


def _require_local_write(request: Request):
    try:
        if not request.client or not ip_address(request.client.host).is_loopback:
            raise ValueError
    except ValueError:
        raise HTTPException(403, "Settings changes are restricted to the local computer")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-origin settings changes are not permitted")


@app.put("/api/content-types/{content_type}")
def update_content_type(content_type: ContentType, body: ContentSettingsUpdate, request: Request,
                        channel: str = "us-economy"):
    _require_local_write(request)
    if channel not in load_channels(settings.channels_file):
        raise HTTPException(404, "Channel not found")
    if not settings.database_url.startswith("postgresql"):
        raise HTTPException(503, "PostgreSQL is required for settings")
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO content_type_settings(channel_id,content_type,enabled,daily_goal)
                VALUES (:channel,:type,:enabled,:goal) ON CONFLICT(channel_id,content_type)
                DO UPDATE SET enabled=EXCLUDED.enabled,daily_goal=EXCLUDED.daily_goal"""),
                {"channel": channel, "type": content_type.value, "enabled": body.enabled, "goal": body.daily_goal})
    finally:
        engine.dispose()
    return {"channel": channel, "content_type": content_type.value, **body.model_dump(),
            "automatic_production_available": False}


@app.get("/api/content-plans")
def content_plans(channel: str = "us-economy", limit: int = 50):
    if channel not in load_channels(settings.channels_file):
        raise HTTPException(404, "Channel not found")
    if not settings.database_url.startswith("postgresql"):
        raise HTTPException(503, "PostgreSQL is required for content plans")
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""SELECT plan_id,content_type,status,stage,topics,ranking_snapshot,duration_seconds,video_path,
                youtube_video_id,error,attempts,created_at,updated_at FROM content_plans
                WHERE channel_id=:channel ORDER BY created_at DESC LIMIT :limit"""),
                {"channel": channel, "limit": max(1, min(limit, 200))}).mappings()
            return [dict(row) for row in rows]
    finally:
        engine.dispose()


@app.post("/api/content-plans/{plan_id}/retry")
def retry_content_plan(plan_id: UUID, request: Request):
    _require_local_write(request)
    if not settings.database_url.startswith("postgresql"):
        raise HTTPException(503, "PostgreSQL is required for content plans")
    from sqlalchemy import create_engine
    from .content_queue import ContentQueue
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        try:
            ContentQueue(engine).retry(str(plan_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    finally:
        engine.dispose()
    return {"plan_id": str(plan_id), "status": "planned", "note": "A worker must be started separately."}


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
    table = "".join("<tr>" + "".join(f"<td>{escape(str(value if value is not None else ''))}</td>" for value in
        (r['channel_id'], r['job_date'], r['status'], r.get('attempts', 0), r.get('error'))) + "</tr>" for r in rows)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Woori YouTube Agent</title>
    <style>body{{font:15px system-ui;margin:3rem;background:#101827;color:#e5e7eb}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.7rem;border-bottom:1px solid #334155;text-align:left}}.pill{{color:#7dd3fc}}</style></head>
    <body><h1>Woori YouTube Agent</h1><p class='pill'>Automatic three-format production is not yet enabled.</p>
    <h2>Now Trends content settings</h2><div id='settings'>Loading…</div><p id='message'></p>
    <h2>Content plans</h2><div id='plans'>Loading…</div><h2>Legacy jobs</h2><table><thead><tr><th>Channel</th><th>Date</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead><tbody>{table}</tbody></table>
    <script>
    async function load() {{
      const specs = await (await fetch('/api/content-types')).json();
      const root = document.getElementById('settings'); root.replaceChildren();
      for (const spec of specs) {{
        const form = document.createElement('form');
        const name = document.createElement('strong'); name.textContent = spec.content_type + ' ';
        const goal = document.createElement('input'); goal.type = 'number'; goal.min = '0'; goal.value = spec.daily_goal;
        const enabled = document.createElement('input'); enabled.type = 'checkbox'; enabled.checked = spec.enabled;
        const label = document.createElement('label'); label.append(enabled, ' Enabled ');
        const button = document.createElement('button'); button.textContent = 'Save goal';
        form.append(name, 'Daily goal ', goal, label, button); root.append(form);
        form.onsubmit = async (event) => {{ event.preventDefault();
          const response = await fetch('/api/content-types/' + encodeURIComponent(spec.content_type), {{method:'PUT', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{daily_goal:Number(goal.value),enabled:enabled.checked}})}});
          document.getElementById('message').textContent = response.ok ? 'Settings saved. Automatic production remains unavailable.' : 'Could not save settings.';
        }};
      }}
      const plans = await (await fetch('/api/content-plans')).json();
      const list = document.getElementById('plans'); list.replaceChildren();
      if (!Array.isArray(plans) || !plans.length) {{ list.textContent = 'No content plans.'; return; }}
      for (const plan of plans) {{
        const row = document.createElement('div'); const details = document.createElement('pre');
        details.textContent = JSON.stringify(plan, null, 2); row.append(details);
        if (['blocked','failed'].includes(plan.status) && !plan.youtube_video_id) {{
          const button = document.createElement('button'); button.textContent = 'Queue retry after reviewing artifacts';
          button.onclick = async () => {{ const r = await fetch('/api/content-plans/' + encodeURIComponent(plan.plan_id) + '/retry', {{method:'POST'}});
            document.getElementById('message').textContent = r.ok ? 'Queued for retry; start a worker separately.' : 'Retry was not allowed.'; if (r.ok) load(); }};
          row.append(button);
        }} list.append(row);
      }}
    }} load().catch(() => document.getElementById('message').textContent = 'Unable to load status.');
    </script></body></html>"""
