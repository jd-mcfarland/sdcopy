from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdcopy.config import state_dir
from sdcopy.util import atomic_write

STATUSES = (
    "running",
    "success",
    "failed",
    "held",
    "safe_to_remove",
    "unmount_failed",
)


@dataclass
class Job:
    id: str
    device: str
    uuid: str = ""
    nickname: str = ""
    status: str = "running"
    started_at: str = ""
    finished_at: str = ""
    src: str = ""
    dest: str = ""
    bytes: int | None = None
    file_count: int | None = None
    rsync_exit: int | None = None
    summary_path: str = ""
    error: str = ""
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def jobs_dir() -> Path:
    path = state_dir() / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def new_job_id(device: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe = "".join(ch if ch.isalnum() else "-" for ch in device).strip("-") or "dev"
    return f"{stamp}-{safe}"


def create_job(**kwargs: Any) -> Job:
    started = kwargs.pop("started_at", None) or datetime.now(timezone.utc).isoformat(timespec="seconds")
    job_id = kwargs.pop("id", None) or new_job_id(str(kwargs.get("device") or "dev"))
    job = Job(id=job_id, started_at=started, **kwargs)
    save_job(job)
    return job


def save_job(job: Job) -> Path:
    path = job_path(job.id)
    atomic_write(path, json.dumps(job.to_dict(), indent=2) + "\n")
    return path


def finish_job(job: Job, status: str, *, error: str = "") -> Job:
    job.status = status
    job.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if error:
        job.error = error
    save_job(job)
    return job


def load_job(job_id: str) -> Job | None:
    path = job_path(job_id)
    if not path.exists():
        return None
    return job_from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_jobs(limit: int = 50) -> list[Job]:
    files = sorted(jobs_dir().glob("*.json"), reverse=True)
    jobs: list[Job] = []
    for path in files:
        try:
            jobs.append(job_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if len(jobs) >= limit:
            break
    jobs.sort(key=lambda job: job.started_at, reverse=True)
    return jobs


def job_from_dict(data: dict[str, Any]) -> Job:
    return Job(
        id=str(data.get("id") or ""),
        device=str(data.get("device") or ""),
        uuid=str(data.get("uuid") or ""),
        nickname=str(data.get("nickname") or ""),
        status=str(data.get("status") or "running"),
        started_at=str(data.get("started_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
        src=str(data.get("src") or ""),
        dest=str(data.get("dest") or ""),
        bytes=data.get("bytes"),
        file_count=data.get("file_count"),
        rsync_exit=data.get("rsync_exit"),
        summary_path=str(data.get("summary_path") or ""),
        error=str(data.get("error") or ""),
        dry_run=bool(data.get("dry_run", False)),
        extra=dict(data.get("extra") or {}),
    )
