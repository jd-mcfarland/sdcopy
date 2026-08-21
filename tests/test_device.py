from __future__ import annotations

import json

from sdcopy.device import DeviceFacts, destination_mount_ok, inspect_device, list_removable_partitions, normalize_kernel


LSBLK = {
    "blockdevices": [
        {
            "name": "sda",
            "type": "disk",
            "tran": "usb",
            "children": [
                {
                    "name": "sda1",
                    "path": "/dev/sda1",
                    "type": "part",
                    "uuid": "AAAA-1111",
                    "label": "SONY",
                    "fstype": "exfat",
                    "size": 128000000000,
                    "mountpoint": "/media/nas/SONY",
                }
            ],
        },
        {
            "name": "nvme0n1",
            "type": "disk",
            "tran": "nvme",
            "children": [
                {
                    "name": "nvme0n1p1",
                    "type": "part",
                    "uuid": "system-uuid",
                    "fstype": "ext4",
                    "size": 500000000000,
                    "mountpoint": "/",
                }
            ],
        },
    ]
}


def test_normalize_kernel():
    assert normalize_kernel("/dev/sda1") == "sda1"
    assert normalize_kernel("dev-sda1.device") == "sda1"
    assert normalize_kernel("mmcblk0p1") == "mmcblk0p1"


def test_inspect_and_list(monkeypatch):
    from sdcopy import device as device_mod
    from sdcopy.util import run_cmd
    import subprocess

    def fake_run(argv, timeout=30, check=False):
        if argv[0] == "lsblk":
            return subprocess.CompletedProcess(argv, 0, json.dumps(LSBLK), "")
        return subprocess.CompletedProcess(argv, 1, "", "err")

    monkeypatch.setattr(device_mod, "run_cmd", fake_run)
    facts = inspect_device("sda1")
    assert facts is not None
    assert facts.uuid == "AAAA-1111"
    assert facts.label == "SONY"
    listed = list_removable_partitions()
    assert [item.kernel for item in listed] == ["sda1"]


def test_destination_rejects_root_filesystem(monkeypatch, tmp_path):
    from sdcopy import device as device_mod
    import subprocess

    dest = tmp_path / "landing"
    dest.mkdir()

    def fake_run(argv, timeout=30, check=False):
        if argv[0] == "findmnt" and "-T" in argv:
            return subprocess.CompletedProcess(argv, 0, "/\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(device_mod, "run_cmd", fake_run)
    ok, reason = destination_mount_ok(str(dest), require_mount=True)
    assert not ok
    assert "root filesystem" in reason


def test_destination_ok_when_on_data_mount(monkeypatch, tmp_path):
    from sdcopy import device as device_mod
    import subprocess

    dest = tmp_path / "landing"
    dest.mkdir()

    def fake_run(argv, timeout=30, check=False):
        if argv[0] == "findmnt" and "-T" in argv:
            return subprocess.CompletedProcess(argv, 0, "/mnt/photos\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(device_mod, "run_cmd", fake_run)
    ok, reason = destination_mount_ok(str(dest), require_mount=True)
    assert ok, reason
