from __future__ import annotations

from pathlib import Path

import pytest

from sdcopy.paths import render_template, unique_dest


def test_render_template_tokens():
    from datetime import datetime

    name = render_template(
        "{nickname}_{date}_{time}",
        nickname="Sony A7 main",
        when=datetime(2026, 8, 21, 13, 5, 9),
    )
    assert name == "Sony_A7_main_20260821_130509"


def test_unknown_token_rejected():
    with pytest.raises(ValueError, match="unknown naming token"):
        render_template("{nickname}_{foo}")


def test_unique_dest_appends_counter(tmp_path: Path):
    (tmp_path / "card_1").mkdir()
    first = unique_dest(tmp_path, "fresh")
    assert first == tmp_path / "fresh"
    first.mkdir()
    second = unique_dest(tmp_path, "fresh")
    assert second == tmp_path / "fresh_2"
    second.mkdir()
    third = unique_dest(tmp_path, "fresh")
    assert third == tmp_path / "fresh_3"
