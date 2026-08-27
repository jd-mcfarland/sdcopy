from __future__ import annotations

from pathlib import Path

from sdcopy.config import (
    Card,
    destination_allowed,
    effective_settings,
    load_config,
    save_config,
    set_config_value,
    upsert_card,
    get_card,
)


def test_overlay_config_roundtrip(isolated_state: Path):
    config = load_config()
    config.destination_root = "/mnt/photos/PhotoLandingZone"
    config.email.to = "ops@example.com"
    save_config(config)
    loaded = load_config()
    assert loaded.destination_root == "/mnt/photos/PhotoLandingZone"
    assert loaded.email.to == "ops@example.com"


def test_set_dotted_key(isolated_state: Path):
    config = load_config()
    config = set_config_value(config, "email.to", "a@b.c")
    config = set_config_value(config, "auto_unmount", "false")
    config = set_config_value(config, "mount_wait_seconds", "90")
    assert config.email.to == "a@b.c"
    assert config.auto_unmount is False
    assert config.mount_wait_seconds == 90


def test_per_card_overrides(isolated_state: Path):
    config = load_config()
    config.destination_root = "/mnt/photos"
    config.auto_unmount = True
    config.naming_template = "{nickname}_{date}"
    card = Card(
        uuid="AAAA-1111",
        nickname="Backup card",
        destination_root="/mnt/photos/backup",
        auto_unmount=False,
    )
    settings = effective_settings(config, card)
    assert settings.destination_root == "/mnt/photos/backup"
    assert settings.auto_unmount is False
    assert settings.naming_template == "{nickname}_{date}"
    assert settings.nickname == "Backup card"


def test_upsert_card(isolated_state: Path):
    upsert_card(Card(uuid="AAAA-1111", nickname="One"))
    upsert_card(Card(uuid="AAAA-1111", nickname="One renamed"))
    card = get_card("AAAA-1111")
    assert card is not None
    assert card.nickname == "One renamed"


def test_destination_must_be_under_allowed_root(isolated_state: Path):
    config = load_config()
    config.destination_root = "/mnt/photos/PhotoLandingZone"
    ok, _ = destination_allowed(config, "/mnt/photos/PhotoLandingZone/sony")
    assert ok
    ok, reason = destination_allowed(config, "/tmp/elsewhere")
    assert not ok
    assert "outside allowed roots" in reason
