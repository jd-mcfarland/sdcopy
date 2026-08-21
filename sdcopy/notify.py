from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sdcopy.config import Config
from sdcopy.jobs import Job

log = logging.getLogger("sdcopy")


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def append_log(config: Config, message: str) -> None:
    log.info(message)
    log_dir = Path(config.log_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "sdcopy.log").open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        pass


def notify_job(config: Config, job: Job) -> None:
    subject, body = render_notice(job)
    append_log(config, f"job {job.id} {job.status}: {job.error or job.dest}")
    send_email(config, subject, body)


def render_notice(job: Job) -> tuple[str, str]:
    name = job.nickname or job.uuid or job.device
    if job.status == "held":
        subject = "sdcopy: new card needs onboarding"
        body = (
            f"A card was inserted that is not onboarded yet.\n\n"
            f"Device: {job.device}\nUUID: {job.uuid or '(none)'}\n"
            f"Open the local sdcopy UI to name this card before it will copy.\n"
        )
        if job.error:
            body += f"\n{job.error}\n"
        return subject, body
    if job.status in {"success", "safe_to_remove"}:
        subject = "sdcopy: copy completed"
        extra = "It is safe to remove the card." if job.status == "safe_to_remove" else "Unmount was skipped."
        body = (
            f"Copy of {name} completed.\n\n"
            f"Destination: {job.dest}\n"
            f"Files: {job.file_count if job.file_count is not None else 'unknown'}\n"
            f"Bytes: {job.bytes if job.bytes is not None else 'unknown'}\n"
            f"{extra}\n"
        )
        return subject, body
    if job.status == "unmount_failed":
        subject = "sdcopy: copied but unmount failed"
        body = (
            f"Copy of {name} finished, but the card could not be unmounted.\n\n"
            f"Destination: {job.dest}\n"
            f"Error: {job.error or 'unmount failed'}\n"
            f"Do not pull the card until it is unmounted safely.\n"
        )
        return subject, body
    subject = "sdcopy: copy failed"
    body = (
        f"Copy of {name} failed.\n\n"
        f"Device: {job.device}\n"
        f"Destination: {job.dest or '(not created)'}\n"
        f"Error: {job.error or job.status}\n"
        f"Leave the card inserted.\n"
    )
    return subject, body


def send_email(config: Config, subject: str, body: str) -> None:
    if not config.email.enabled or not config.email.to:
        return
    if shutil.which("msmtp") is None:
        log.warning("msmtp not installed; skipping email")
        return
    import subprocess

    message = f"Subject: {subject}\n\n{body}"
    argv = ["msmtp"]
    if config.email.msmtp_account:
        argv.extend(["-a", config.email.msmtp_account])
    argv.append(config.email.to)
    result = subprocess.run(argv, input=message, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log.warning("msmtp failed: %s", result.stderr.strip())
