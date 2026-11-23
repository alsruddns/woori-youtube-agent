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
