from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/woori_youtube.db")
    artifacts_dir: Path = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
    channels_file: Path = Path(os.getenv("CHANNELS_FILE", "config/channels.yaml"))
    codex_command: str = os.getenv("CODEX_COMMAND", "codex")
    codex_enabled: bool = os.getenv("CODEX_ENABLED", "false").lower() == "true"
    codex_timeout_seconds: int = int(os.getenv("CODEX_TIMEOUT_SECONDS", "1800"))
    youtube_channel_id: str = os.getenv("US_YOUTUBE_CHANNEL_ID", "")
    youtube_enabled: bool = os.getenv("YOUTUBE_ENABLED", "false").lower() == "true"
    youtube_schedule_enabled: bool = os.getenv("YOUTUBE_SCHEDULE_ENABLED", "false").lower() == "true"
    youtube_public_preflight_passed: bool = os.getenv("YOUTUBE_PUBLIC_PREFLIGHT_PASSED", "false").lower() == "true"
    youtube_privacy_status: str = os.getenv("YOUTUBE_PRIVACY_STATUS", "private")
    youtube_client_secrets_file: Path = Path(os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "secrets/youtube-client-secret.json"))
    youtube_token_file: Path = Path(os.getenv("YOUTUBE_TOKEN_FILE", "secrets/youtube-token.json"))
    youtube_privacy_status: str = os.getenv("YOUTUBE_PRIVACY_STATUS", "private")
    ffmpeg_bin: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    video_width: int = int(os.getenv("VIDEO_WIDTH", "1920"))
    video_height: int = int(os.getenv("VIDEO_HEIGHT", "1080"))
    kokoro_voice: str = os.getenv("KOKORO_VOICE", "af_heart")
    target_minutes: int = int(os.getenv("VIDEO_TARGET_MINUTES", "15"))
    publish_hour: int = int(os.getenv("YOUTUBE_DEFAULT_PUBLISH_HOUR", "18"))
    publish_minute: int = int(os.getenv("YOUTUBE_DEFAULT_PUBLISH_MINUTE", "0"))


settings = Settings()
