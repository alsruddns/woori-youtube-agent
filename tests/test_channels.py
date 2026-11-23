from pathlib import Path

from woori_youtube.channels import load_channels


def test_channels_keep_locale_category_and_voice_provider_config():
    channels = load_channels(Path("config/channels.yaml"))
    us = channels["us-economy"]
    assert us.locale == "en-US"
    assert ("https://www.whitehouse.gov/briefings-statements/feed/", "politics") in us.rss_feeds
    assert us.tts_engine == "kokoro"
    korean = channels["kr-economy-politics"]
    assert korean.enabled is False
    assert korean.tts_engine == "external-korean-provider"
