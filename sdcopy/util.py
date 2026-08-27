from __future__ import annotations

import os
import subprocess
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_cmd(
    argv: list[str],
    *,
    timeout: float | None = 30,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def parse_mode(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 8)
