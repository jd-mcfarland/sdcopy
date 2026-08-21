from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdcopy.config import save_config, save_cards, config_from_dict, Card


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("SDCOPY_STATE_DIR", str(state))
    monkeypatch.setenv("SDCOPY_ETC_CONFIG", str(tmp_path / "no-etc.json"))
    return state


def write_config(state: Path, **overrides):
    data = config_from_dict(
        {
            "destination_root": str(state / "dest"),
            "require_destination_mount": False,
            "owner": "",
            "group": "",
            "email": {"enabled": False, "to": ""},
            "log_dir": str(state / "logs"),
            **overrides,
        }
    )
    (state / "dest").mkdir(exist_ok=True)
    save_config(data)
    return data


def write_card(**kwargs) -> Card:
    card = Card(**kwargs)
    save_cards([card])
    return card
