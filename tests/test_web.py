from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import write_config


def test_dashboard_and_onboard(isolated_state: Path):
    write_config(isolated_state)
    from sdcopy.web.app import app

    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert "Landing zone" in home.text

    response = client.post(
        "/onboard",
        data={
            "uuid": "AAAA-1111",
            "nickname": "Sony A7 main",
            "action": "save",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    cards = client.get("/cards")
    assert "Sony A7 main" in cards.text
    assert "AAAA-1111" in cards.text


def test_settings_save(isolated_state: Path):
    write_config(isolated_state)
    from sdcopy.web.app import app

    client = TestClient(app)
    dest = isolated_state / "landing"
    dest.mkdir()
    response = client.post(
        "/settings",
        data={
            "destination_root": str(dest),
            "naming_template": "{nickname}_{date}_{time}",
            "unknown_card_policy": "hold",
            "source_mode": "entire_card",
            "mount_wait_seconds": "45",
            "listen_host": "127.0.0.1",
            "listen_port": "8743",
            "dir_mode": "2775",
            "file_mode": "0664",
            "log_dir": str(isolated_state / "logs"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from sdcopy.config import load_config

    assert load_config().mount_wait_seconds == 45
    assert load_config().destination_root == str(dest)
