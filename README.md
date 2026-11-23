> **Development status:** the legacy daily pipeline is still economy/politics based and enforces one job per day. It does not satisfy the Now Trends production requirements and must not be enabled for unattended production. The Trends collector below is an independent, partial implementation. No video or upload readiness is implied.

# Woori YouTube Agent

Local-first automation for daily US economy and politics news videos. Channel settings are locale-based so additional languages and country channels can be enabled without changing the pipeline. The US English channel is enabled; Korean is scaffolded and disabled pending Korean source feeds and editorial settings.

## Safety defaults

- No paid OpenAI API key. Script generation invokes an installed, ChatGPT-signed-in Codex CLI only when `CODEX_ENABLED=true`.
- YouTube integration and scheduled publication are off by default; privacy defaults to `private`.
- Public uploads require `YOUTUBE_PUBLIC_PREFLIGHT_PASSED=true`, which should only be set after a controlled OAuth/public-upload test in the target channel.
- Research/script/media failure prevents upload. One upload per channel and date is enforced in the durable ledger.
- This is news commentary software, not investment advice. Article text and third-party video are not reused as narration or footage.

## Windows quick start

1. Install Python 3.12+, Git, and FFmpeg/ffprobe. Use the PostgreSQL server already running on the local PC.
2. Create a virtual environment and install `pip install -e ".[dev]"`.
3. Copy `.env.example` to `.env` and set `DATABASE_URL` to the existing PostgreSQL host, port, database, username, and password. Create the `woori_youtube` database if it does not exist, then run `alembic upgrade head`. Docker Compose is optional and only needed if you choose to run a separate PostgreSQL container.
4. Install a local Codex CLI and sign in with the ChatGPT account. Confirm `codex exec` works interactively before setting `CODEX_ENABLED=true`. Do not add an API key.
5. Install Kokoro model dependencies and verify local synthesis before enabling the scheduled task.
6. Run `uvicorn woori_youtube.api:app --app-dir src --host 127.0.0.1 --port 8000` for the dashboard/API.
7. Run a research-only dry run: `python -m woori_youtube.cli research --channel us-economy` with `PYTHONPATH=src`.
8. Configure YouTube OAuth as described in `docs/operations.md`. Test private upload first, then perform a controlled public-upload test before enabling unattended public posts.
9. Only after each manual stage passes, install the daily Windows task using `scripts/install-scheduler.ps1`.

The application reads `.env` from the project working directory. The scheduled task sets that directory as its working directory, so it uses the same settings. The optional Docker Compose database maps to port 5434; if you use it, change the sample `DATABASE_URL` port to 5434.

## Run

```powershell
$env:PYTHONPATH = "src"
python -m pytest
uvicorn woori_youtube.api:app --host 127.0.0.1 --port 8000
```

See `docs/operations.md` for credential setup, channel expansion, retries, and preflight steps.

## Experimental Google Trends collection

After configuring a working PostgreSQL connection and applying Alembic migrations, run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m woori_youtube.cli trends --channel us-economy --region US
```

Each successful collection stores a snapshot and each fetch failure stores an error. The public RSS endpoint does not establish a 4-hour or 24-hour window or active status; these fields are not inferred. The volume value is the lower bound of a displayed bucket, not an exact count. The collector is not yet connected to topic selection or scheduling. Existing per-day job and upload constraints remain in place.

Uploads additionally require `US_YOUTUBE_CHANNEL_ID` to match the authenticated channel. Changing OAuth scopes may require a new interactive authorization; do not delete an existing token without reviewing it first. Public publishing remains opt-in.

## Authentication and queue development status

`python -m woori_youtube.cli youtube-auth` starts the Google Desktop OAuth flow and then verifies the configured channel ID. This does not upload a video. The authentication token is stored in the ignored path configured by `YOUTUBE_TOKEN_FILE`.

Migration `0003_production_queue` adds an event-keyed queue with transactional claiming and leases. Event keys must be assigned through verified editorial review; the current collector does not identify events and the queue is not connected to the legacy runner. Expired claims are blocked for review rather than retried automatically. There is no automatic daily target, verified topic selection, or publisher integration yet.

For development, `enqueue-reviewed-trend --keyword ... --event-key ... --reason ...` admits an independently reviewed event only if its keyword is in the latest successful RSS snapshot, no older than 30 minutes. It records the selection and rejects an existing event key atomically. `trend-worker-once --worker ...` claims a job, collects a fresh RSS snapshot, saves its unverified news leads under the job's artifact directory and blocks for independent research. These commands do not establish the requested 4-hour/24-hour or active filters, automate editorial review, render a video, or upload. They are not unattended production.

FFmpeg validation checks duration, video resolution, and presence of an audio stream; these checks do not establish audible narration, synchronized subtitles, media rights, factual accuracy, or video integrity. Human and additional automated checks remain necessary.

The renderer bases approximate subtitle cue timing on the actual WAV duration and writes a sidecar SRT. It distributes words evenly within each scene; this is not word-level alignment and needs review. The existing text-card renderer is a technical prototype, not a completed visual production or quality gate.

Install the collection-only scheduled task with `scripts/install-trends-scheduler.ps1` after the database and migrations are ready. It runs every 30 minutes, prevents overlapping instances, and logs under the ignored `data/` directory. It does not create or publish videos. Run `Unregister-ScheduledTask -TaskName WooriYouTubeAgent-Trends` to remove it. Python 3.12 is required for the current Kokoro dependency.
