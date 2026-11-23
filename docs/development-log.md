# Development log

## P1-CODEX-001 — initial local implementation

This checkout was empty at the start of work: it contained only `.git`, had no commits, and had no configured remote. GitHub could not be reached from this environment (`git ls-remote` failed during DNS/network startup). Implementation below was created against the supplied specification, not against unobserved remote source.

### Phase 1 — foundation and research

- Added FastAPI service, a small HTML job dashboard, channel catalog, RSS/Atom ingestion, stable item deduplication, research package export, feed/date checks, SQLite development ledger, and PostgreSQL ledger adapter.
- Channels are catalog-driven. US English is enabled; Korean economy/politics is preconfigured but disabled and has no feeds yet.
- Tests cover feed parsing, dedup keys, source diversity, state transitions, crash recovery, and upload idempotency.

### Phase 2 — script generation and verification

- Added Codex CLI `exec` integration using the locally signed-in CLI; no OpenAI API key or paid API is configured.
- Prompt supports locale and channel metadata, economy and politics coverage, and source-linked factual claims.
- Hard gate checks required JSON shape, scene narration and visual direction, duration, source URL membership, exact evidence excerpt membership in RSS title/summary, numeric tokens against evidence, required source categories, and a channel-localized disclaimer.
- Script output and gate report are retained by channel/date. Invalid scripts stop before TTS and upload.

### Phase 3 — media

- Added optional local Kokoro synthesis, Matplotlib chart utility, original branded thumbnail, still-card scenes, FFmpeg rendering, approximate burned-in subtitles, and ffprobe duration/size checks.
- Media dependencies and model weights must be installed/downloaded locally. Render currently uses original text cards, not licensed footage or live market data charts; the chart helper needs a trusted data input adapter.

### Phase 4 — YouTube

- Added desktop OAuth consent flow, persisted resumable chunk uploads, thumbnail upload, future publish scheduling, and channel/date duplicate ledger.
- Defaults to disabled/private. Public uploads hard-fail until a separate preflight flag is set after a controlled test on the actual account. Google's API policy changed on November 2, 2026: unverified projects are no longer restricted to private uploads. No OAuth client or account consent was present here, so account-specific upload/public status remains unverified.

### Phase 5 — unattended operation

- Added Windows Task Scheduler install/uninstall scripts, retry-on-process-failure settings, startup recovery of interrupted jobs, persistent status/error/audit records, and a local dashboard. Recorded validation/configuration blocks exit cleanly so Task Scheduler does not blindly retry them.
- The job is fail-closed: Codex disabled, insufficient research, script/media checks, or YouTube configuration block publication.
- This environment did not have `ffmpeg`, PostgreSQL, YouTube credentials, or the Google API client. The installed Codex CLI reported ChatGPT login, but a real invocation was denied access to the user's Codex state database. Full unattended run and 7/30-day soak tests cannot be claimed until run on the user's Windows machine with those components.

### Verification

- Automated tests: 13 deterministic unit tests passed; they do not call external services. The FastAPI health handler returned `ok` when invoked directly; a full TestClient HTTP smoke request hung under this hosted runner and still needs a local serving check.
- Codex CLI 0.169.0 is installed and `codex login status` reported ChatGPT login. A tiny real `codex exec` smoke run failed because this hosted workspace could not open the user's Codex state database (`Access is denied`). The flags were verified with `codex exec --help`; execution must be rechecked from the normal Windows session.
- Live RSS, Codex CLI unattended usage limits, Kokoro model download, FFmpeg rendering, PostgreSQL migrations, OAuth consent, account-specific public upload, API quota, and actual scheduled publishing require local setup and remain unverified.
