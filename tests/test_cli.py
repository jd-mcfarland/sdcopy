from __future__ import annotations

from pathlib import Path

from sdcopy.cli import main
from tests.conftest import write_config


def test_cli_onboard_and_settings(isolated_state: Path, capsys):
    write_config(isolated_state)
    assert main(["onboard", "AAAA-1111", "--nickname", "Sony A7 main"]) == 0
    assert main(["cards"]) == 0
    out = capsys.readouterr().out
    assert "Sony A7 main" in out
    assert main(["settings", "set", "email.to", "ops@example.com"]) == 0
    assert main(["settings"]) == 0
    out = capsys.readouterr().out
    assert "ops@example.com" in out
