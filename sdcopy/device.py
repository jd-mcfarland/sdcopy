from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from sdcopy.util import run_cmd

REMOVABLE_FSTYPES = {"vfat", "exfat", "ntfs", "msdos", "fuseblk"}


@dataclass
class DeviceFacts:
    kernel: str
    path: str
    uuid: str | None
    label: str | None
    fstype: str | None
    size: str | None
    size_bytes: int | None
    mountpoint: str | None
    parent: str | None
    transport: str | None

    @property
    def is_mounted(self) -> bool:
        return bool(self.mountpoint)


def normalize_kernel(name: str) -> str:
    text = name.strip()
    if text.endswith(".device"):
        text = text[: -len(".device")]
    if text.startswith("/dev/"):
        text = text[5:]
    if text.startswith("dev-"):
        text = text[4:]
    return text


def device_path(kernel: str) -> Path:
    return Path("/dev") / normalize_kernel(kernel)


def inspect_device(kernel: str) -> DeviceFacts | None:
    kernel = normalize_kernel(kernel)
    payload = _lsblk_json()
    if not payload:
        return _inspect_fallback(kernel)
    for node, parent, transport in _walk_blockdevices(payload.get("blockdevices") or []):
        if node.get("name") == kernel or _basename(node.get("path")) == kernel:
            return _facts_from_node(node, parent=parent, transport=transport)
    return None


def list_removable_partitions() -> list[DeviceFacts]:
    payload = _lsblk_json()
    if not payload:
        return []
    found: list[DeviceFacts] = []
    for node, parent, transport in _walk_blockdevices(payload.get("blockdevices") or []):
        if node.get("type") != "part":
            continue
        fstype = (node.get("fstype") or "").lower()
        name = str(node.get("name") or "")
        is_mmc = name.startswith("mmcblk") and "p" in name
        is_usb = (transport or "").lower() == "usb"
        if fstype not in REMOVABLE_FSTYPES:
            continue
        if not (is_usb or is_mmc):
            continue
        found.append(_facts_from_node(node, parent=parent, transport=transport))
    return found


def find_mount(device: str) -> str | None:
    path = str(device_path(device))
    result = run_cmd(["findmnt", "-n", "-o", "TARGET", "-S", path])
    if result.returncode != 0:
        return None
    target = result.stdout.strip().splitlines()
    return target[0] if target else None


def mount_target_for_path(path: str | Path) -> str | None:
    result = run_cmd(["findmnt", "-n", "-o", "TARGET", "-T", str(path)])
    if result.returncode != 0:
        return None
    lines = result.stdout.strip().splitlines()
    return lines[0] if lines else None


def destination_mount_ok(dest_root: str, *, require_mount: bool) -> tuple[bool, str]:
    path = Path(dest_root).expanduser()
    if not dest_root.strip():
        return False, "destination_root is not configured"
    if not path.exists():
        return False, f"destination does not exist: {path}"
    if not path.is_dir():
        return False, f"destination is not a directory: {path}"
    if not require_mount:
        return True, ""
    target = mount_target_for_path(path)
    if target is None:
        return False, f"could not determine mount for {path}"
    if target == "/":
        return False, (
            f"destination {path} is on the root filesystem; "
            "the NAS volume may be unmounted"
        )
    return True, ""


def wait_for_mount(kernel: str, timeout_seconds: int) -> str | None:
    deadline = time.time() + max(timeout_seconds, 0)
    while True:
        mounted = find_mount(kernel)
        if mounted:
            return mounted
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _lsblk_json() -> dict | None:
    result = run_cmd(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,PATH,UUID,LABEL,FSTYPE,SIZE,MOUNTPOINT,TYPE,TRAN,PKNAME",
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _walk_blockdevices(nodes: list[dict], parent: dict | None = None, transport: str | None = None):
    for node in nodes:
        node_transport = node.get("tran") or transport
        yield node, parent, node_transport
        children = node.get("children") or []
        yield from _walk_blockdevices(children, parent=node, transport=node_transport)


def _facts_from_node(node: dict, *, parent: dict | None, transport: str | None) -> DeviceFacts:
    name = str(node.get("name") or "")
    path = node.get("path") or f"/dev/{name}"
    size_bytes = node.get("size")
    try:
        size_bytes_int = int(size_bytes) if size_bytes is not None else None
    except (TypeError, ValueError):
        size_bytes_int = None
    return DeviceFacts(
        kernel=name,
        path=str(path),
        uuid=_blank_to_none(node.get("uuid")),
        label=_blank_to_none(node.get("label")),
        fstype=_blank_to_none(node.get("fstype")),
        size=_human_size(size_bytes_int),
        size_bytes=size_bytes_int,
        mountpoint=_blank_to_none(node.get("mountpoint")),
        parent=_blank_to_none((parent or {}).get("name") or node.get("pkname")),
        transport=_blank_to_none(transport),
    )


def _inspect_fallback(kernel: str) -> DeviceFacts | None:
    path = device_path(kernel)
    if not path.exists():
        return None
    return DeviceFacts(
        kernel=kernel,
        path=str(path),
        uuid=None,
        label=None,
        fstype=None,
        size=None,
        size_bytes=None,
        mountpoint=find_mount(kernel),
        parent=None,
        transport=None,
    )


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _basename(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).name


def _human_size(size_bytes: int | None) -> str | None:
    if size_bytes is None:
        return None
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return None
