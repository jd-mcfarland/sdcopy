from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

from sdcopy.config import (
    SOURCE_DCIM,
    UNKNOWN_COPY,
    Config,
    effective_settings,
    get_card,
    load_config,
)
from sdcopy.device import (
    DeviceFacts,
    destination_mount_ok,
    inspect_device,
    normalize_kernel,
    wait_for_mount,
)
from sdcopy.jobs import Job, create_job, finish_job
from sdcopy.lock import ingest_lock
from sdcopy.notify import append_log, configure_logging, notify_job
from sdcopy.paths import render_template, unique_dest
from sdcopy.rsync import apply_permissions, build_argv, parse_stats, run_rsync, verify_copy
from sdcopy.util import parse_mode, run_cmd


class IngestError(Exception):
    def __init__(self, message: str, *, status: str = "failed"):
        super().__init__(message)
        self.status = status


def run(device: str, *, dry_run: bool = False, send_notice: bool = True) -> Job:
    configure_logging()
    config = load_config()
    kernel = normalize_kernel(device)
    with ingest_lock():
        job = create_job(device=kernel, status="running", dry_run=dry_run)
        try:
            _ingest(config, job, kernel, dry_run=dry_run)
        except IngestError as exc:
            finish_job(job, exc.status, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - last-resort job failure
            finish_job(job, "failed", error=str(exc))
        else:
            if job.status == "running":
                finish_job(job, "success")
    if send_notice:
        notify_job(config, job)
    return job


def _ingest(config: Config, job: Job, kernel: str, *, dry_run: bool) -> None:
    append_log(config, f"ingest start device={kernel} dry_run={dry_run} job={job.id}")
    mountpoint = wait_for_mount(kernel, config.mount_wait_seconds)
    facts = inspect_device(kernel)
    if facts is None:
        facts = DeviceFacts(
            kernel=kernel,
            path=f"/dev/{kernel}",
            uuid=None,
            label=None,
            fstype=None,
            size=None,
            size_bytes=None,
            mountpoint=mountpoint,
            parent=None,
            transport=None,
        )
    if mountpoint and not facts.mountpoint:
        facts.mountpoint = mountpoint
    job.src = facts.mountpoint or ""
    job.uuid = facts.uuid or ""
    job.nickname = facts.label or ""

    if not facts.mountpoint:
        raise IngestError(
            f"timed out waiting for /dev/{kernel} to mount",
            status="failed",
        )
    if not facts.uuid:
        raise IngestError(
            f"/dev/{kernel} has no filesystem UUID; reformat or onboard is unsafe",
            status="failed",
        )

    card = get_card(facts.uuid)
    if card is None:
        if config.unknown_card_policy != UNKNOWN_COPY:
            job.uuid = facts.uuid
            job.nickname = facts.label or facts.uuid
            raise IngestError(
                f"unknown card {facts.uuid} held for onboarding",
                status="held",
            )
        nickname = facts.label or facts.uuid
        settings = effective_settings(config, None, nickname=nickname)
    elif not card.enabled:
        job.nickname = card.nickname
        raise IngestError(f"card {card.nickname} is disabled", status="held")
    else:
        job.nickname = card.nickname
        job.uuid = card.uuid
        settings = effective_settings(config, card)

    ok, reason = destination_mount_ok(
        settings.destination_root,
        require_mount=settings.require_destination_mount,
    )
    if not ok:
        raise IngestError(reason)

    src = _source_path(Path(facts.mountpoint), settings.source_mode)
    when = datetime.now()
    folder = render_template(
        settings.naming_template,
        nickname=settings.nickname,
        label=facts.label or "",
        uuid=facts.uuid,
        when=when,
    )
    dest = unique_dest(Path(settings.destination_root), folder)
    job.dest = str(dest)
    job.nickname = settings.nickname

    planned = build_argv(src, dest, checksum=settings.verify_checksum, dry_run=dry_run)
    job.extra["rsync_argv"] = planned
    if dry_run:
        finish_job(job, "success")
        append_log(config, f"dry-run dest={dest} argv={' '.join(planned)}")
        return

    dest.mkdir(parents=True, exist_ok=True)
    result = run_rsync(src, dest, checksum=settings.verify_checksum, dry_run=False)
    job.rsync_exit = result.exit_code
    summary_path = dest / "transfer_summary.txt"
    summary = result.stdout
    if result.stderr:
        summary += ("\n" if summary else "") + result.stderr
    if result.vanished:
        summary += "\nWARNING: rsync reported vanished source files (exit 24)\n"
    summary_path.write_text(summary, encoding="utf-8")
    job.summary_path = str(summary_path)
    bytes_copied, file_count = parse_stats(result.stdout)
    job.bytes = bytes_copied
    job.file_count = file_count

    if not result.ok:
        raise IngestError(f"rsync exited {result.exit_code}: {result.stderr.strip() or result.stdout.strip()}")

    if settings.verify_checksum:
        verified, verify_error = verify_copy(src, dest)
        if not verified:
            raise IngestError(verify_error)

    try:
        apply_permissions(
            dest,
            owner=settings.owner,
            group=settings.group,
            dir_mode=parse_mode(settings.dir_mode),
            file_mode=parse_mode(settings.file_mode),
        )
    except Exception as exc:
        raise IngestError(f"failed to set destination permissions: {exc}") from exc

    os.sync()
    if not settings.auto_unmount:
        finish_job(job, "success")
        return

    unmounted, unmount_error = unmount_device(facts)
    if unmounted:
        finish_job(job, "safe_to_remove")
        return
    finish_job(job, "unmount_failed", error=unmount_error)


def _source_path(mountpoint: Path, source_mode: str) -> Path:
    if source_mode != SOURCE_DCIM:
        return mountpoint
    dcim = mountpoint / "DCIM"
    if not dcim.is_dir():
        raise IngestError(f"DCIM folder not found on {mountpoint}")
    return dcim


def unmount_device(facts: DeviceFacts) -> tuple[bool, str]:
    os.sync()
    block = facts.path
    if shutil.which("udisksctl"):
        result = run_cmd(["udisksctl", "unmount", "-b", block], timeout=120)
        if result.returncode == 0:
            _try_eject(facts)
            return True, ""
        udisks_error = result.stderr.strip() or result.stdout.strip()
    else:
        udisks_error = "udisksctl not available"
    if facts.mountpoint:
        result = run_cmd(["umount", facts.mountpoint], timeout=120)
        if result.returncode == 0:
            _try_eject(facts)
            return True, ""
        return False, result.stderr.strip() or udisks_error
    return False, udisks_error or "unmount failed"


def _try_eject(facts: DeviceFacts) -> None:
    disk = facts.parent
    if not disk:
        return
    disk_path = f"/dev/{disk}"
    if shutil.which("udisksctl"):
        run_cmd(["udisksctl", "power-off", "-b", disk_path], timeout=60)
        return
    if shutil.which("eject"):
        run_cmd(["eject", disk_path], timeout=60)


def spawn(device: str, *, dry_run: bool = False) -> int:
    import subprocess
    import sys

    argv = [sys.executable, "-m", "sdcopy.ingest", normalize_kernel(device)]
    if dry_run:
        argv.append("--dry-run")
    proc = subprocess.Popen(
        argv,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a removable partition into the landing zone")
    parser.add_argument("device", help="kernel name such as sda1 or mmcblk0p1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args(argv)
    job = run(args.device, dry_run=args.dry_run, send_notice=not args.no_notify)
    print(f"{job.status}\t{job.id}\t{job.dest or job.error}")
    if job.status in {"failed"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
