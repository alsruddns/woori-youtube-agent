from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PublishBlocked(RuntimeError):
    pass


def authorize(client_secrets: Path, token_file: Path, *, port: int = 0) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("Install the Google API client dependencies first.") from exc
    scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    credentials = Credentials.from_authorized_user_file(str(token_file), scopes) if token_file.exists() else None
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes)
            credentials = flow.run_local_server(port=port, access_type="offline", prompt="consent")
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def verify_channel(credentials: Any, expected_channel_id: str) -> None:
    if not expected_channel_id.strip():
        raise PublishBlocked("Expected YouTube channel ID must be configured before upload.")
    from googleapiclient.discovery import build
    response = build("youtube", "v3", credentials=credentials).channels().list(
        part="id,snippet", mine=True, maxResults=50).execute()
    matches = [item for item in response.get("items", []) if item.get("id") == expected_channel_id]
    if len(matches) != 1:
        raise PublishBlocked("Authenticated YouTube channel does not match the configured channel ID.")


def upload_video(path: Path, metadata: dict[str, Any], credentials: Any, *, privacy_status: str = "private", publish_at: datetime | None = None, public_preflight_passed: bool = False, session_file: Path | None = None) -> str:
    if privacy_status == "public" and not public_preflight_passed:
        raise PublishBlocked("Public upload is disabled until a controlled public-upload preflight has been recorded.")
    if publish_at and not public_preflight_passed:
        raise PublishBlocked("Scheduled publication is disabled until a controlled public-upload preflight has been recorded.")
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted, or public.")
    if publish_at:
        if publish_at.tzinfo is None or publish_at <= datetime.now(timezone.utc):
            raise ValueError("publish_at must be a future timezone-aware datetime.")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError("Install the Google authentication client first.") from exc
    body: dict[str, Any] = {"snippet": {"title": metadata["title"], "description": metadata["description"],
                                         "tags": metadata.get("tags", []), "categoryId": "25"},
                            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False}}
    if publish_at:
        body["status"].update({"privacyStatus": "private", "publishAt": publish_at.astimezone(timezone.utc).isoformat()})
    session = AuthorizedSession(credentials)
    total = path.stat().st_size
    mime_type = "video/mp4"
    session_file = session_file or path.with_suffix(".upload-session.json")
    session_file.parent.mkdir(parents=True, exist_ok=True)
    upload_url: str | None = None
    offset = 0
    if session_file.exists():
        try:
            upload_url = json.loads(session_file.read_text(encoding="utf-8")).get("upload_url")
        except (OSError, json.JSONDecodeError):
            upload_url = None
    if not upload_url:
        response = session.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            json=body,
            headers={"X-Upload-Content-Length": str(total), "X-Upload-Content-Type": mime_type,
                     "Content-Type": "application/json; charset=UTF-8"}, timeout=60)
        response.raise_for_status()
        upload_url = response.headers.get("Location")
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload session URL.")
        session_file.write_text(json.dumps({"upload_url": upload_url, "size": total}), encoding="utf-8")
    # Ask YouTube for the acknowledged offset so a restarted process continues from its cursor.
    cursor = session.put(upload_url, headers={"Content-Length": "0", "Content-Range": f"bytes */{total}"}, timeout=60)
    if cursor.status_code in (200, 201):
        session_file.unlink(missing_ok=True)
        return cursor.json()["id"]
    if cursor.status_code == 308:
        acknowledged = cursor.headers.get("Range", "")
        if acknowledged.startswith("bytes=0-"):
            offset = int(acknowledged.partition("-")[2]) + 1
    elif cursor.status_code in (404, 410):
        session_file.unlink(missing_ok=True)
        raise PublishBlocked("YouTube upload session expired; verify YouTube Studio before manually retrying to avoid a duplicate upload.")
    else:
        cursor.raise_for_status()
    chunk_size = 8 * 1024 * 1024
    consecutive_failures = 0
    with path.open("rb") as video:
        while offset < total:
            video.seek(offset)
            chunk = video.read(min(chunk_size, total - offset))
            end = offset + len(chunk) - 1
            response = session.put(upload_url, data=chunk,
                headers={"Content-Length": str(len(chunk)), "Content-Type": mime_type,
                         "Content-Range": f"bytes {offset}-{end}/{total}"}, timeout=180)
            if response.status_code in (200, 201):
                session_file.unlink(missing_ok=True)
                return response.json()["id"]
            if response.status_code == 308:
                acknowledged = response.headers.get("Range", "")
                next_offset = int(acknowledged.partition("-")[2]) + 1 if acknowledged.startswith("bytes=0-") else end + 1
                if next_offset > offset:
                    consecutive_failures = 0
                offset = next_offset
                continue
            if response.status_code >= 500:
                consecutive_failures += 1
                if consecutive_failures > 5:
                    raise RuntimeError(f"YouTube upload failed repeatedly with HTTP {response.status_code}.")
                time.sleep(min(2 ** consecutive_failures, 30))
                continue
            response.raise_for_status()
    raise RuntimeError("YouTube upload ended without a completed video response.")


def upload_thumbnail(video_id: str, thumbnail: Path, credentials: Any) -> None:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if not thumbnail.is_file():
        raise FileNotFoundError(thumbnail)
    youtube = build("youtube", "v3", credentials=credentials)
    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
