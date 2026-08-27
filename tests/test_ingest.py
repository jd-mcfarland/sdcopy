from __future__ import annotations

from pathlib import Path

from sdcopy.config import Card
from sdcopy.device import DeviceFacts
from sdcopy.ingest import run
from sdcopy.rsync import RsyncResult
from tests.conftest import write_card, write_config


def _facts(mount: str, uuid: str = "AAAA-1111") -> DeviceFacts:
    return DeviceFacts(
        kernel="sda1",
        path="/dev/sda1",
        uuid=uuid,
        label="SONY",
        fstype="exfat",
        size="128.0 GB",
        size_bytes=128000000000,
        mountpoint=mount,
        parent="sda",
        transport="usb",
    )


def _patch_common(monkeypatch, facts: DeviceFacts, *, rsync=None, unmount=None, verify=True):
    from sdcopy import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "wait_for_mount", lambda *a, **k: facts.mountpoint)
    monkeypatch.setattr(ingest_mod, "inspect_device", lambda kernel: facts)
    monkeypatch.setattr(ingest_mod, "destination_mount_ok", lambda *a, **k: (True, ""))
    monkeypatch.setattr(
        ingest_mod,
        "run_rsync",
        rsync
        or (
            lambda *a, **k: RsyncResult(
                0,
                "Number of regular files transferred: 3\nTotal transferred file size: 3000 bytes\n",
                "",
                ["rsync"],
            )
        ),
    )
    monkeypatch.setattr(ingest_mod, "verify_copy", lambda *a, **k: (verify, "" if verify else "mismatch"))
    monkeypatch.setattr(ingest_mod, "apply_permissions", lambda *a, **k: None)
    monkeypatch.setattr(ingest_mod, "unmount_device", unmount or (lambda facts: (True, "")))
    monkeypatch.setattr(ingest_mod, "notify_job", lambda *a, **k: None)


def test_unknown_card_is_held(isolated_state: Path, monkeypatch, tmp_path):
    write_config(isolated_state)
    src = tmp_path / "card"
    src.mkdir()
    _patch_common(monkeypatch, _facts(str(src)))
    called = {"rsync": False}

    from sdcopy import ingest as ingest_mod

    def boom(*a, **k):
        called["rsync"] = True
        raise AssertionError("rsync should not run")

    monkeypatch.setattr(ingest_mod, "run_rsync", boom)
    job = run("sda1", send_notice=False)
    assert job.status == "held"
    assert called["rsync"] is False
    assert "AAAA-1111" in (job.error + job.uuid)


def test_known_card_copies_and_unmounts(isolated_state: Path, monkeypatch, tmp_path):
    write_config(isolated_state)
    write_card(uuid="AAAA-1111", nickname="Sony A7 main")
    src = tmp_path / "card"
    src.mkdir()
    (src / "DCIM").mkdir()
    unmounted = {"ok": False}

    def fake_unmount(facts):
        unmounted["ok"] = True
        return True, ""

    _patch_common(monkeypatch, _facts(str(src)), unmount=fake_unmount)
    job = run("sda1", send_notice=False)
    assert job.status == "safe_to_remove"
    assert unmounted["ok"] is True
    assert job.nickname == "Sony A7 main"
    assert Path(job.dest).name.startswith("Sony_A7_main_")
    assert Path(job.summary_path).is_file()


def test_rsync_failure_does_not_unmount(isolated_state: Path, monkeypatch, tmp_path):
    write_config(isolated_state)
    write_card(uuid="AAAA-1111", nickname="Sony A7 main")
    src = tmp_path / "card"
    src.mkdir()
    unmounted = {"ok": False}

    def fail_rsync(*a, **k):
        return RsyncResult(23, "", "disk full", ["rsync"])

    def fake_unmount(facts):
        unmounted["ok"] = True
        return True, ""

    _patch_common(monkeypatch, _facts(str(src)), rsync=fail_rsync, unmount=fake_unmount)
    job = run("sda1", send_notice=False)
    assert job.status == "failed"
    assert unmounted["ok"] is False
    assert job.rsync_exit == 23


def test_disabled_card_is_held(isolated_state: Path, monkeypatch, tmp_path):
    write_config(isolated_state)
    write_card(uuid="AAAA-1111", nickname="Old card", enabled=False)
    src = tmp_path / "card"
    src.mkdir()
    _patch_common(monkeypatch, _facts(str(src)))
    job = run("sda1", send_notice=False)
    assert job.status == "held"
    assert "disabled" in job.error


def test_dry_run_skips_copy(isolated_state: Path, monkeypatch, tmp_path):
    write_config(isolated_state)
    write_card(uuid="AAAA-1111", nickname="Sony A7 main")
    src = tmp_path / "card"
    src.mkdir()
    called = {"rsync": 0}

    def count_rsync(*a, **k):
        called["rsync"] += 1
        return RsyncResult(0, "", "", ["rsync"])

    _patch_common(monkeypatch, _facts(str(src)), rsync=count_rsync)
    job = run("sda1", dry_run=True, send_notice=False)
    assert job.status == "success"
    assert job.dry_run is True
    assert called["rsync"] == 0
    assert "rsync_argv" in job.extra
