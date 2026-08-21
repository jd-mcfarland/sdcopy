from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sdcopy.util import run_cmd

FAT_FSTYPES = {"vfat", "exfat", "msdos", "ntfs", "fuseblk"}
RSYNC_OK = 0
RSYNC_VANISHED = 24

DEFAULT_EXCLUDES = (
    "System Volume Information",
    ".Trash*",
    ".Trashes",
    ".rsync-partial",
    ".Spotlight-V100",
    ".fseventsd",
)


@dataclass
class RsyncResult:
    exit_code: int
    stdout: str
    stderr: str
    argv: list[str]

    @property
    def ok(self) -> bool:
        return self.exit_code in {RSYNC_OK, RSYNC_VANISHED}

    @property
    def vanished(self) -> bool:
        return self.exit_code == RSYNC_VANISHED


def build_argv(
    src: Path,
    dest: Path,
    *,
    checksum: bool = False,
    dry_run: bool = False,
    itemize: bool = False,
) -> list[str]:
    argv = [
        "rsync",
        "-rt",
        "--modify-window=1",
        "--partial",
        "--partial-dir=.rsync-partial",
        "--info=stats2",
    ]
    if checksum:
        argv.append("--checksum")
    if dry_run:
        argv.append("--dry-run")
    if itemize:
        argv.append("--itemize-changes")
    for pattern in DEFAULT_EXCLUDES:
        argv.append(f"--exclude={pattern}")
    argv.append(str(src) + "/")
    argv.append(str(dest) + "/")
    return argv


def run_rsync(
    src: Path,
    dest: Path,
    *,
    checksum: bool = False,
    dry_run: bool = False,
) -> RsyncResult:
    argv = build_argv(src, dest, checksum=checksum, dry_run=dry_run)
    dest.mkdir(parents=True, exist_ok=True)
    result = run_cmd(argv, timeout=None)
    return RsyncResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        argv=argv,
    )


def verify_copy(src: Path, dest: Path) -> tuple[bool, str]:
    argv = build_argv(src, dest, checksum=True, dry_run=True, itemize=True)
    result = run_cmd(argv, timeout=None)
    if result.returncode not in {RSYNC_OK, RSYNC_VANISHED}:
        return False, f"verify rsync exited {result.returncode}: {result.stderr.strip()}"
    pending: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith(">f") or line.startswith("<f"):
            pending.append(line)
    if pending:
        preview = "; ".join(pending[:8])
        return False, f"checksum verify found files that still differ: {preview}"
    return True, ""


def parse_stats(output: str) -> tuple[int | None, int | None]:
    file_count = None
    total_bytes = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("number of regular files transferred:"):
            file_count = _int_from_line(stripped)
        elif stripped.lower().startswith("total transferred file size:"):
            total_bytes = _int_from_line(stripped.replace(",", ""))
        elif stripped.lower().startswith("total file size:"):
            if total_bytes is None:
                total_bytes = _int_from_line(stripped.replace(",", ""))
    return total_bytes, file_count


def _int_from_line(line: str) -> int | None:
    digits = "".join(ch for ch in line if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def apply_permissions(
    dest: Path,
    *,
    owner: str,
    group: str,
    dir_mode: int,
    file_mode: int,
) -> None:
    if owner or group:
        for dirpath, dirnames, filenames in os.walk(dest):
            path = Path(dirpath)
            _chown(path, owner, group)
            os.chmod(path, dir_mode)
            for name in dirnames:
                child = path / name
                _chown(child, owner, group)
                os.chmod(child, dir_mode)
            for name in filenames:
                child = path / name
                _chown(child, owner, group)
                os.chmod(child, file_mode)
    else:
        for dirpath, dirnames, filenames in os.walk(dest):
            path = Path(dirpath)
            os.chmod(path, dir_mode)
            for name in filenames:
                os.chmod(path / name, file_mode)


def _chown(path: Path, owner: str, group: str) -> None:
    uid = -1
    gid = -1
    if owner:
        import pwd

        uid = pwd.getpwnam(owner).pw_uid
    if group:
        import grp

        gid = grp.getgrnam(group).gr_gid
    if uid != -1 or gid != -1:
        os.chown(path, uid, gid)
