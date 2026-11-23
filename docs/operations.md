# Local operations and required account setup

## Existing local PostgreSQL

Use the PostgreSQL server already installed on the PC; Docker Compose is optional. Set `DATABASE_URL` in `.env` to the server's actual port, database, username, and password. The sample uses `localhost:5432`; create the `woori_youtube` database first if needed, then run `alembic upgrade head`. If the existing server uses another port, replace `5432`. The optional `docker-compose.yml` maps its separate container to port `5434`.

## Codex Plus integration

The application starts the local `codex exec` CLI with a bounded timeout, read-only sandbox, and no interactive approval prompt. The user must install the supported Codex CLI, authenticate interactively with the ChatGPT Plus account, and verify a small `codex exec` run in a terminal. There is no documented guarantee here that consumer ChatGPT Plus scheduled tasks can be triggered from a Windows scheduled process or that the local CLI has unlimited unattended quota. This project uses the local CLI process, not ChatGPT's web scheduler. Check the CLI's current login and usage behavior on the target PC before turning on `CODEX_ENABLED`; rate limits, interactive reauthentication, policy prompts, and OS approval settings can stop a scheduled run. Any such stop leaves the job blocked/failed and does not publish.

## YouTube OAuth and public access

1. In Google Cloud Console, create/select a project, enable YouTube Data API v3, configure the OAuth consent screen, and create an OAuth client of type **Desktop app**.
2. Download the client JSON to `secrets/youtube-client-secret.json`. Do not commit it. Keep `YOUTUBE_ENABLED=false` until ready for an interactive authorization.
3. The first upload opens a local browser consent window and stores refresh credentials at `secrets/youtube-token.json`; this is the user's required initial OAuth approval.
4. Start with `YOUTUBE_PRIVACY_STATUS=private` and `YOUTUBE_SCHEDULE_ENABLED=false`, upload a short test, and inspect it in YouTube Studio. This keeps the test private with no scheduled public time.
5. Google's current YouTube Data API revision history says that, as of November 2, 2026, uploads from unverified API projects are no longer restricted to private visibility. That replaces the older private-only restriction. The user's own channel/project permission still cannot be verified without OAuth credentials, so perform a controlled public test and inspect YouTube Studio before setting `YOUTUBE_PUBLIC_PREFLIGHT_PASSED=true`. Google still recommends a compliance audit for continued API access and quota use. See [YouTube Data API revision history](https://developers.google.com/youtube/data/revision_history?hl=en).
6. Only after that test, set `YOUTUBE_SCHEDULE_ENABLED=true` to assign a future publish time in the channel's local timezone. Confirm the scheduled time in Studio after the first scheduled upload.

## Enabling Korean channel

Add official Korean government/statistical agency/central bank feeds and reviewed publisher feeds to `config/channels.yaml`, classify each feed as economy or politics, then switch `kr-economy-politics.enabled` to true. Populate Korean titles, disclaimer translations, Kokoro Korean language/voice support, font settings, and a Korean script prompt review before producing Korean public videos. The current rendering and voice selection are English-centric.

## Recovery and observation

- The uploader keeps its ignored `*.upload-session.json` record after completion, including the video ID and a fingerprint of the video and metadata. Keep this record with the artifact: it prevents an ordinary restart from creating a second upload. A mismatched, unreadable, legacy, or expired record requires inspecting YouTube Studio before any deliberate retry. A crash before the initial resumable-session URL is saved can still leave an uncertain upload, so never blindly recreate a missing record after an interrupted upload.

- Dashboard: `http://127.0.0.1:8000/`; JSON status: `/api/jobs` and `/api/jobs/{job_id}`.
- Job records preserve state, timestamps, attempt count, and error. The next process start converts orphaned `running` jobs to `retry` for operator visibility.
- Scheduler config retries a failed process three times at ten-minute intervals. Duplicate upload ledger blocks a second upload for the same channel/date.
- Review `artifacts/<channel>/<date>/` and `data/runner.log` after a blocked job. Fix configuration/data and re-run deliberately.
- Keep PC awake, logged in as the account owning credentials, online, and connected to power. Task Scheduler cannot recover from missing network, OS sleep, revoked consent, exhausted quotas, or unavailable model downloads on its own.

## Multi-language expansion

Each channel defines locale, language name, country, timezone, categories, target duration, feeds, and enabled state. Add one channel entry per country/language. Store localized title, description, disclaimer, fonts/voices, source feeds, and publication schedule by channel. Do not translate the US script into Korean when the underlying story is country-specific; collect and validate Korean sources separately.
