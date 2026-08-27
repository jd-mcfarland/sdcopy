from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


_TOKEN = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


def render_template(
    template: str,
    *,
    nickname: str = "",
    label: str = "",
    uuid: str = "",
    when: datetime | None = None,
) -> str:
    when = when or datetime.now()
    values = {
        "nickname": _slug(nickname) or "card",
        "label": _slug(label) or _slug(nickname) or "card",
        "uuid": _slug(uuid) or "unknown",
        "date": when.strftime("%Y%m%d"),
        "time": when.strftime("%H%M%S"),
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"unknown naming token {{{key}}}")
        return values[key]

    rendered = _TOKEN.sub(replace, template).strip()
    if not rendered:
        raise ValueError("naming template produced an empty name")
    return rendered


def unique_dest(root: Path, name: str) -> Path:
    dest = root / name
    if not dest.exists():
        return dest
    index = 2
    while True:
        candidate = root / f"{name}_{index}"
        if not candidate.exists():
            return candidate
        index += 1


def _slug(value: str) -> str:
    text = value.strip().replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text
