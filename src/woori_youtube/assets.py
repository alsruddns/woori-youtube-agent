"""Track the provenance and review status of scene artwork."""
from pathlib import Path
from urllib.parse import urlparse


def validate_scene_assets(scenes: list[dict]) -> list[str]:
    errors = []
    if not scenes:
        return ["At least one scene is required."]
    for index, scene in enumerate(scenes, 1):
        asset = scene.get("asset") if isinstance(scene, dict) else None
        if not isinstance(asset, dict):
            errors.append(f"Scene {index} has no reviewed asset.")
            continue
        path = Path(str(asset.get("path", "")))
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            errors.append(f"Scene {index} asset is missing or not a supported image.")
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
    return errors
