from __future__ import annotations

import argparse
import json
import sys

from sdcopy.config import (
    Card,
    delete_card,
    get_card,
    load_cards,
    load_config,
    save_config,
    set_config_value,
    upsert_card,
)
from sdcopy.device import list_removable_partitions
from sdcopy.ingest import run as run_ingest
from sdcopy.jobs import list_jobs, load_job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdcopy", description="SD card ingest and local setup UI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="list inserted removable partitions")

    sub.add_parser("cards", help="list onboarded cards")

    onboard = sub.add_parser("onboard", help="register a card UUID")
    onboard.add_argument("uuid")
    onboard.add_argument("--nickname", required=True)
    onboard.add_argument("--label", default="")
    onboard.add_argument("--notes", default="")
    onboard.add_argument("--destination-root", default=None)
    onboard.add_argument("--naming-template", default=None)

    card = sub.add_parser("card", help="update or forget an onboarded card")
    card.add_argument("uuid")
    card.add_argument("--nickname")
    card.add_argument("--enable", action="store_true")
    card.add_argument("--disable", action="store_true")
    card.add_argument("--forget", action="store_true")
    card.add_argument("--notes")

    settings = sub.add_parser("settings", help="show or change global settings")
    settings.add_argument("set", nargs="?", choices=["set"])
    settings.add_argument("key", nargs="?")
    settings.add_argument("value", nargs="?")

    jobs = sub.add_parser("jobs", help="list recent ingest jobs")
    jobs.add_argument("--limit", type=int, default=20)
    jobs.add_argument("job_id", nargs="?")

    ingest = sub.add_parser("ingest", help="ingest a device now")
    ingest.add_argument("device")
    ingest.add_argument("--dry-run", action="store_true")
    ingest.add_argument("--no-notify", action="store_true")

    web = sub.add_parser("web", help="run the localhost UI")
    web.add_argument("--host")
    web.add_argument("--port", type=int)

    args = parser.parse_args(argv)
    handler = {
        "devices": cmd_devices,
        "cards": cmd_cards,
        "onboard": cmd_onboard,
        "card": cmd_card,
        "settings": cmd_settings,
        "jobs": cmd_jobs,
        "ingest": cmd_ingest,
        "web": cmd_web,
    }[args.command]
    return handler(args)


def cmd_devices(_args: argparse.Namespace) -> int:
    cards = {card.uuid: card for card in load_cards()}
    devices = list_removable_partitions()
    if not devices:
        print("No removable partitions found.")
        return 0
    for facts in devices:
        card = cards.get(facts.uuid or "")
        state = "known" if card and card.enabled else "disabled" if card else "unknown"
        nickname = card.nickname if card else "-"
        print(
            f"{facts.kernel}\t{facts.uuid or '-'}\t{facts.label or '-'}\t"
            f"{facts.fstype or '-'}\t{facts.size or '-'}\t{facts.mountpoint or '-'}\t"
            f"{state}\t{nickname}"
        )
    return 0


def cmd_cards(_args: argparse.Namespace) -> int:
    cards = load_cards()
    if not cards:
        print("No onboarded cards.")
        return 0
    for card in cards:
        flag = "on" if card.enabled else "off"
        print(f"{card.uuid}\t{card.nickname}\t{flag}\t{card.label}")
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    existing = get_card(args.uuid)
    card = Card(
        uuid=args.uuid,
        nickname=args.nickname,
        label=args.label or (existing.label if existing else ""),
        enabled=True,
        destination_root=args.destination_root if args.destination_root is not None else (existing.destination_root if existing else None),
        naming_template=args.naming_template if args.naming_template is not None else (existing.naming_template if existing else None),
        notes=args.notes or (existing.notes if existing else ""),
        auto_unmount=existing.auto_unmount if existing else None,
        source_mode=existing.source_mode if existing else None,
    )
    upsert_card(card)
    print(f"onboarded {card.uuid} as {card.nickname}")
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    if args.forget:
        if delete_card(args.uuid):
            print(f"forgot {args.uuid}")
            return 0
        print(f"no card {args.uuid}", file=sys.stderr)
        return 1
    card = get_card(args.uuid)
    if card is None:
        print(f"no card {args.uuid}", file=sys.stderr)
        return 1
    if args.nickname:
        card.nickname = args.nickname
    if args.notes is not None:
        card.notes = args.notes
    if args.enable and args.disable:
        print("use only one of --enable/--disable", file=sys.stderr)
        return 1
    if args.enable:
        card.enabled = True
    if args.disable:
        card.enabled = False
    upsert_card(card)
    print(f"updated {card.uuid} ({card.nickname})")
    return 0


def cmd_settings(args: argparse.Namespace) -> int:
    config = load_config()
    if args.set == "set":
        if not args.key or args.value is None:
            print("usage: sdcopy settings set KEY VALUE", file=sys.stderr)
            return 2
        config = set_config_value(config, args.key, args.value)
        save_config(config)
        print(f"set {args.key}")
        return 0
    print(json.dumps(config.to_dict(), indent=2))
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    if args.job_id:
        job = load_job(args.job_id)
        if job is None:
            print(f"no job {args.job_id}", file=sys.stderr)
            return 1
        print(json.dumps(job.to_dict(), indent=2))
        return 0
    jobs = list_jobs(limit=args.limit)
    if not jobs:
        print("No jobs yet.")
        return 0
    for job in jobs:
        print(f"{job.started_at}\t{job.status}\t{job.nickname or job.uuid or job.device}\t{job.dest or job.error}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    job = run_ingest(args.device, dry_run=args.dry_run, send_notice=not args.no_notify)
    print(json.dumps(job.to_dict(), indent=2))
    return 0 if job.status != "failed" else 1


def cmd_web(args: argparse.Namespace) -> int:
    from sdcopy.web.app import run_server

    config = load_config()
    host = args.host or config.listen.host
    port = args.port or config.listen.port
    run_server(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
