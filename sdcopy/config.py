from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sdcopy.util import atomic_write

DEFAULT_ETC_CONFIG = Path("/etc/sdcopy/config.json")
DEFAULT_STATE_DIR = Path("/var/lib/sdcopy")

UNKNOWN_HOLD = "hold"
UNKNOWN_COPY = "copy"
SOURCE_ENTIRE = "entire_card"
SOURCE_DCIM = "dcim_only"

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def state_dir() -> Path:
    return Path(os.environ.get("SDCOPY_STATE_DIR", str(DEFAULT_STATE_DIR)))


def etc_config_path() -> Path:
    return Path(os.environ.get("SDCOPY_ETC_CONFIG", str(DEFAULT_ETC_CONFIG)))


@dataclass
class EmailConfig:
    enabled: bool = True
    to: str = ""
    msmtp_account: str = "default"


@dataclass
class ListenConfig:
    host: str = "127.0.0.1"
    port: int = 8743
    token: str = ""


@dataclass
class Config:
    destination_root: str = ""
    require_destination_mount: bool = True
    naming_template: str = "{nickname}_{date}_{time}"
    unknown_card_policy: str = UNKNOWN_HOLD
    auto_unmount: bool = True
    verify_checksum: bool = True
    source_mode: str = SOURCE_ENTIRE
    owner: str = "nas"
    group: str = "sdcopy"
    dir_mode: str = "2775"
    file_mode: str = "0664"
    email: EmailConfig = field(default_factory=EmailConfig)
    listen: ListenConfig = field(default_factory=ListenConfig)
    mount_wait_seconds: int = 60
    log_dir: str = "/var/log/sdcopy"
    allowed_roots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Card:
    uuid: str
    nickname: str
    label: str = ""
    enabled: bool = True
    destination_root: str | None = None
    naming_template: str | None = None
    auto_unmount: bool | None = None
    source_mode: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EffectiveSettings:
    destination_root: str
    naming_template: str
    auto_unmount: bool
    source_mode: str
    nickname: str
    verify_checksum: bool
    require_destination_mount: bool
    owner: str
    group: str
    dir_mode: str
    file_mode: str
    mount_wait_seconds: int


def default_config() -> Config:
    return Config()


def _merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _email_from_dict(data: dict[str, Any]) -> EmailConfig:
    return EmailConfig(
        enabled=bool(data.get("enabled", True)),
        to=str(data.get("to", "")),
        msmtp_account=str(data.get("msmtp_account", "default")),
    )


def _listen_from_dict(data: dict[str, Any]) -> ListenConfig:
    return ListenConfig(
        host=str(data.get("host", "127.0.0.1")),
        port=int(data.get("port", 8743)),
        token=str(data.get("token", "")),
    )


def config_from_dict(data: dict[str, Any]) -> Config:
    defaults = asdict(Config())
    merged = _merge_dict(defaults, data)
    return Config(
        destination_root=str(merged.get("destination_root", "")),
        require_destination_mount=bool(merged.get("require_destination_mount", True)),
        naming_template=str(merged.get("naming_template", "{nickname}_{date}_{time}")),
        unknown_card_policy=str(merged.get("unknown_card_policy", UNKNOWN_HOLD)),
        auto_unmount=bool(merged.get("auto_unmount", True)),
        verify_checksum=bool(merged.get("verify_checksum", True)),
        source_mode=str(merged.get("source_mode", SOURCE_ENTIRE)),
        owner=str(merged.get("owner", "nas")),
        group=str(merged.get("group", "sdcopy")),
        dir_mode=str(merged.get("dir_mode", "2775")),
        file_mode=str(merged.get("file_mode", "0664")),
        email=_email_from_dict(merged.get("email") or {}),
        listen=_listen_from_dict(merged.get("listen") or {}),
        mount_wait_seconds=int(merged.get("mount_wait_seconds", 60)),
        log_dir=str(merged.get("log_dir", "/var/log/sdcopy")),
        allowed_roots=[str(p) for p in (merged.get("allowed_roots") or [])],
    )


def card_from_dict(data: dict[str, Any]) -> Card:
    uuid = str(data.get("uuid") or "").strip()
    if not uuid:
        raise ValueError("card uuid is required")
    nickname = str(data.get("nickname") or "").strip()
    if not nickname:
        raise ValueError("card nickname is required")
    auto_unmount = data.get("auto_unmount", None)
    return Card(
        uuid=uuid,
        nickname=nickname,
        label=str(data.get("label") or ""),
        enabled=bool(data.get("enabled", True)),
        destination_root=_optional_str(data.get("destination_root")),
        naming_template=_optional_str(data.get("naming_template")),
        auto_unmount=None if auto_unmount is None else bool(auto_unmount),
        source_mode=_optional_str(data.get("source_mode")),
        notes=str(data.get("notes") or ""),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_config() -> Config:
    data = asdict(Config())
    etc = _read_json(etc_config_path())
    if etc:
        data = _merge_dict(data, etc)
    overlay = _read_json(state_dir() / "config.json")
    if overlay:
        data = _merge_dict(data, overlay)
    return config_from_dict(data)


def save_config(config: Config) -> Path:
    path = state_dir() / "config.json"
    atomic_write(path, json.dumps(config.to_dict(), indent=2) + "\n")
    return path


def cards_path() -> Path:
    return state_dir() / "cards.json"


def load_cards() -> list[Card]:
    raw = _read_json(cards_path())
    if not raw:
        return []
    items = raw.get("cards", raw if isinstance(raw, list) else [])
    return [card_from_dict(item) for item in items]


def save_cards(cards: list[Card]) -> Path:
    payload = {"cards": [card.to_dict() for card in cards]}
    path = cards_path()
    atomic_write(path, json.dumps(payload, indent=2) + "\n")
    return path


def get_card(uuid: str) -> Card | None:
    uuid = uuid.strip()
    for card in load_cards():
        if card.uuid == uuid:
            return card
    return None


def upsert_card(card: Card) -> Card:
    cards = [existing for existing in load_cards() if existing.uuid != card.uuid]
    cards.append(card)
    cards.sort(key=lambda item: item.nickname.lower())
    save_cards(cards)
    return card


def delete_card(uuid: str) -> bool:
    cards = load_cards()
    kept = [card for card in cards if card.uuid != uuid]
    if len(kept) == len(cards):
        return False
    save_cards(kept)
    return True


def effective_settings(config: Config, card: Card | None, *, nickname: str | None = None) -> EffectiveSettings:
    if card is None:
        display = nickname or "unknown"
        return EffectiveSettings(
            destination_root=config.destination_root,
            naming_template=config.naming_template,
            auto_unmount=config.auto_unmount,
            source_mode=config.source_mode,
            nickname=display,
            verify_checksum=config.verify_checksum,
            require_destination_mount=config.require_destination_mount,
            owner=config.owner,
            group=config.group,
            dir_mode=config.dir_mode,
            file_mode=config.file_mode,
            mount_wait_seconds=config.mount_wait_seconds,
        )
    return EffectiveSettings(
        destination_root=card.destination_root or config.destination_root,
        naming_template=card.naming_template or config.naming_template,
        auto_unmount=config.auto_unmount if card.auto_unmount is None else card.auto_unmount,
        source_mode=card.source_mode or config.source_mode,
        nickname=card.nickname,
        verify_checksum=config.verify_checksum,
        require_destination_mount=config.require_destination_mount,
        owner=config.owner,
        group=config.group,
        dir_mode=config.dir_mode,
        file_mode=config.file_mode,
        mount_wait_seconds=config.mount_wait_seconds,
    )


def set_config_value(config: Config, dotted_key: str, raw: str) -> Config:
    data = config.to_dict()
    keys = dotted_key.split(".")
    cursor: Any = data
    for key in keys[:-1]:
        if key not in cursor or not isinstance(cursor[key], dict):
            cursor[key] = {}
        cursor = cursor[key]
    leaf = keys[-1]
    cursor[leaf] = _coerce_value(cursor.get(leaf), raw)
    return config_from_dict(data)


def _coerce_value(current: Any, raw: str) -> Any:
    if isinstance(current, bool) or current is None and raw.lower() in {"true", "false"}:
        if raw.lower() in {"true", "1", "yes"}:
            return True
        if raw.lower() in {"false", "0", "no"}:
            return False
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw)
    if isinstance(current, list):
        if not raw.strip():
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def listen_is_loopback(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_HOSTS


def destination_allowed(config: Config, dest_root: str) -> tuple[bool, str]:
    dest = Path(dest_root).expanduser()
    if not dest.is_absolute():
        return False, "destination must be an absolute path"
    allowed = [Path(p).expanduser().resolve() for p in config.allowed_roots if p]
    if not allowed:
        if config.destination_root:
            allowed = [Path(config.destination_root).expanduser().resolve(strict=False)]
        else:
            return True, ""
    try:
        resolved = dest.resolve(strict=False)
    except OSError:
        resolved = dest
    for root in allowed:
        if resolved == root or root in resolved.parents:
            return True, ""
    return False, f"destination {dest} is outside allowed roots"
