from woori_youtube.assets import validate_scene_assets


def test_assets_require_review_and_evidence(tmp_path):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"test")
    asset = {"path": str(image), "creator": "Creator", "rights_type": "licensed",
             "rights_verified": True, "source_url": "https://example.com/image",
             "rights_url": "https://example.com/license", "license": "CC BY 4.0",
             "attribution": "Creator"}
    assert validate_scene_assets([{"asset": asset}]) == []
    asset.pop("attribution")
    asset["rights_verified"] = False
    errors = validate_scene_assets([{"asset": asset}])
    assert any("rights review" in error for error in errors)
    assert any("attribution" in error for error in errors)
    assert validate_scene_assets([{}])


def test_stock_video_requires_rights_and_illustrative_label(tmp_path):
    image = tmp_path / "card.png"
    image.write_bytes(b"image")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")
    asset = {"path": str(image), "creator": "Creator", "rights_type": "original", "rights_verified": True,
             "broll": {"path": str(clip), "creator": "Videographer", "rights_type": "licensed",
                       "rights_verified": True, "license": "Pexels", "attribution": "Creator via Pexels",
                       "source_url": "https://example.com/clip", "rights_url": "https://example.com/license"}}
    assert any("illustrative" in error for error in validate_scene_assets([{"asset": asset}]))
    asset["broll"]["depiction"] = "illustrative"
    assert validate_scene_assets([{"asset": asset}]) == []
    asset["broll"] = [asset["broll"], dict(asset["broll"], start_seconds=4)]
    assert validate_scene_assets([{"asset": asset}]) == []
    asset["broll"][1]["depiction"] = "archive"
    assert any("archive" in error for error in validate_scene_assets([{"asset": asset}]))
    asset["broll"][1]["archive_context"] = "CREW-13 OCT 2026"
    assert validate_scene_assets([{"asset": asset}]) == []
