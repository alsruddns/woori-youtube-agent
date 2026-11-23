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
