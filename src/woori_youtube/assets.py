"""Track the provenance and review status of scene artwork."""
from pathlib import Path
from urllib.parse import urlparse


def validate_scene_assets(scenes: list[dict], *, allow_video: bool = False) -> list[str]:
    errors = []
    if not scenes:
        return ["At least one scene is required."]
    for index, scene in enumerate(scenes, 1):
        asset = scene.get("asset") if isinstance(scene, dict) else None
        if not isinstance(asset, dict):
            errors.append(f"Scene {index} has no reviewed asset.")
            continue
        path = Path(str(asset.get("path", "")))
        supported = {".png", ".jpg", ".jpeg"} | ({".mp4", ".webm", ".mov"} if allow_video else set())
        if not path.is_file() or path.suffix.lower() not in supported:
            errors.append(f"Scene {index} asset is missing or not a supported media file.")
        if asset.get("rights_verified") is not True or not str(asset.get("creator", "")).strip():
            errors.append(f"Scene {index} needs a creator and explicit rights review.")
        kind = asset.get("rights_type")
        if kind not in {"original", "licensed", "public_domain"}:
            errors.append(f"Scene {index} needs a supported rights type.")
        if kind in {"licensed", "public_domain"}:
            for key in ("source_url", "rights_url"):
                parsed = urlparse(str(asset.get(key, "")))
                if parsed.scheme != "https" or not parsed.hostname:
                    errors.append(f"Scene {index} needs a valid {key}.")
        if kind == "licensed" and (not asset.get("license") or not asset.get("attribution")):
            errors.append(f"Scene {index} needs license and attribution details.")
        if path.suffix.lower() in {".mp4", ".webm", ".mov"} and asset.get("depiction") != "illustrative":
            errors.append(f"Scene {index} video must be marked as illustrative stock footage.")
        if asset.get("broll") is not None:
            broll = asset["broll"]
            if not isinstance(broll, dict) or broll.get("broll") is not None:
                errors.append(f"Scene {index} has invalid nested B-roll.")
            else:
                errors.extend(f"Scene {index} B-roll: {error}" for error in
                              validate_scene_assets([{"asset": broll}], allow_video=True))
                if Path(str(broll.get("path", ""))).suffix.lower() not in {".mp4", ".webm", ".mov"}:
                    errors.append(f"Scene {index} B-roll must be a video.")
    return errors
