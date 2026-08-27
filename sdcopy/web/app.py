from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sdcopy import __version__
from sdcopy.config import (
    SOURCE_DCIM,
    SOURCE_ENTIRE,
    UNKNOWN_COPY,
    UNKNOWN_HOLD,
    Card,
    destination_allowed,
    get_card,
    listen_is_loopback,
    load_cards,
    load_config,
    save_config,
    state_dir,
    upsert_card,
    delete_card,
)
from sdcopy.device import inspect_device, list_removable_partitions
from sdcopy.ingest import spawn
from sdcopy.jobs import list_jobs, load_job

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app = FastAPI(title="sdcopy", version=__version__)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _session_secret() -> str:
    path = state_dir() / "web_secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    path.write_text(secret + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return secret


app.add_middleware(SessionMiddleware, secret_key=_session_secret())


@app.middleware("http")
async def token_gate(request: Request, call_next):
    config = load_config()
    if request.url.path.startswith("/static"):
        return await call_next(request)
    if not config.listen.token:
        return await call_next(request)
    if request.url.path == "/login":
        return await call_next(request)
    if request.cookies.get("sdcopy_token") == config.listen.token:
        return await call_next(request)
    return RedirectResponse("/login", status_code=303)


def _flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def _pop_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


def _ctx(request: Request, **extra):
    return {
        "request": request,
        "version": __version__,
        "flash": _pop_flash(request),
        **extra,
    }


def render(request: Request, name: str, **extra):
    return templates.TemplateResponse(request, name, _ctx(request, **extra))


def _device_rows():
    cards = {card.uuid: card for card in load_cards()}
    rows = []
    for facts in list_removable_partitions():
        card = cards.get(facts.uuid or "")
        rows.append({"facts": facts, "card": card})
    return rows


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return render(
        request,
        "dashboard.html",
        devices=_device_rows(),
        jobs=list_jobs(limit=20),
    )


@app.get("/api/status")
async def api_status():
    devices = []
    for row in _device_rows():
        facts = row["facts"]
        card = row["card"]
        devices.append(
            {
                "kernel": facts.kernel,
                "uuid": facts.uuid,
                "label": facts.label,
                "fstype": facts.fstype,
                "size": facts.size,
                "mountpoint": facts.mountpoint,
                "known": card is not None,
                "enabled": None if card is None else card.enabled,
                "nickname": card.nickname if card else None,
            }
        )
    jobs = [job.to_dict() for job in list_jobs(limit=20)]
    return JSONResponse({"devices": devices, "jobs": jobs})


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return render(request, "login.html")


@app.post("/login")
async def login_submit(request: Request, token: Annotated[str, Form()] = ""):
    config = load_config()
    if token != config.listen.token:
        _flash(request, "That token did not match.", "error")
        return RedirectResponse("/login", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("sdcopy_token", token, httponly=True, samesite="lax")
    return response


@app.get("/onboard", response_class=HTMLResponse)
async def onboard_form(request: Request, device: str = "", uuid: str = ""):
    facts = inspect_device(device) if device else None
    if facts is None and uuid:
        for item in list_removable_partitions():
            if item.uuid == uuid:
                facts = item
                break
    existing = get_card(facts.uuid) if facts and facts.uuid else None
    config = load_config()
    return render(
        request,
        "onboard.html",
        facts=facts,
        existing=existing,
        config=config,
        unknown_devices=[row for row in _device_rows() if row["card"] is None],
    )


@app.post("/onboard")
async def onboard_submit(
    request: Request,
    uuid: Annotated[str, Form()],
    nickname: Annotated[str, Form()],
    device: Annotated[str, Form()] = "",
    label: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    destination_root: Annotated[str, Form()] = "",
    naming_template: Annotated[str, Form()] = "",
    source_mode: Annotated[str, Form()] = "",
    auto_unmount: Annotated[str, Form()] = "default",
    action: Annotated[str, Form()] = "save",
):
    uuid = uuid.strip()
    nickname = nickname.strip()
    if not uuid or not nickname:
        _flash(request, "UUID and nickname are required.", "error")
        return RedirectResponse(f"/onboard?device={device}", status_code=303)
    dest = destination_root.strip() or None
    config = load_config()
    if dest:
        allowed, reason = destination_allowed(config, dest)
        if not allowed:
            _flash(request, reason, "error")
            return RedirectResponse(f"/onboard?device={device}", status_code=303)
    auto = None
    if auto_unmount == "yes":
        auto = True
    elif auto_unmount == "no":
        auto = False
    mode = source_mode.strip() or None
    if mode not in {None, SOURCE_ENTIRE, SOURCE_DCIM}:
        mode = None
    existing = get_card(uuid)
    card = Card(
        uuid=uuid,
        nickname=nickname,
        label=label.strip() or (existing.label if existing else ""),
        enabled=True,
        destination_root=dest,
        naming_template=naming_template.strip() or None,
        auto_unmount=auto,
        source_mode=mode,
        notes=notes.strip(),
    )
    upsert_card(card)
    if action == "dry_run" and device:
        spawn(device, dry_run=True)
        _flash(request, f"Saved {nickname}. Dry run started.")
        return RedirectResponse("/", status_code=303)
    if action == "copy" and device:
        spawn(device)
        _flash(request, f"Saved {nickname}. Copy started.")
        return RedirectResponse("/", status_code=303)
    _flash(request, f"Saved {nickname}.")
    return RedirectResponse("/cards", status_code=303)


@app.get("/cards", response_class=HTMLResponse)
async def cards_page(request: Request):
    return render(request, "cards.html", cards=load_cards())


@app.get("/cards/{uuid}", response_class=HTMLResponse)
async def card_edit(request: Request, uuid: str):
    card = get_card(uuid)
    if card is None:
        _flash(request, "That card is not in the registry.", "error")
        return RedirectResponse("/cards", status_code=303)
    return render(request, "card_edit.html", card=card, config=load_config())


@app.post("/cards/{uuid}")
async def card_update(
    request: Request,
    uuid: str,
    nickname: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    destination_root: Annotated[str, Form()] = "",
    naming_template: Annotated[str, Form()] = "",
    source_mode: Annotated[str, Form()] = "",
    auto_unmount: Annotated[str, Form()] = "default",
    enabled: Annotated[str, Form()] = "",
):
    card = get_card(uuid)
    if card is None:
        _flash(request, "That card is not in the registry.", "error")
        return RedirectResponse("/cards", status_code=303)
    dest = destination_root.strip() or None
    config = load_config()
    if dest:
        allowed, reason = destination_allowed(config, dest)
        if not allowed:
            _flash(request, reason, "error")
            return RedirectResponse(f"/cards/{uuid}", status_code=303)
    card.nickname = nickname.strip() or card.nickname
    card.notes = notes.strip()
    card.destination_root = dest
    card.naming_template = naming_template.strip() or None
    card.source_mode = source_mode.strip() or None
    card.enabled = enabled == "on"
    if auto_unmount == "yes":
        card.auto_unmount = True
    elif auto_unmount == "no":
        card.auto_unmount = False
    else:
        card.auto_unmount = None
    upsert_card(card)
    _flash(request, f"Updated {card.nickname}.")
    return RedirectResponse("/cards", status_code=303)


@app.post("/cards/{uuid}/delete")
async def card_delete(request: Request, uuid: str):
    delete_card(uuid)
    _flash(request, "Forgot that card. Already copied folders were left in place.")
    return RedirectResponse("/cards", status_code=303)


@app.post("/ingest/{device}")
async def ingest_now(request: Request, device: str, dry_run: bool = False):
    spawn(device, dry_run=dry_run)
    _flash(request, "Dry run started." if dry_run else "Copy started.")
    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str):
    job = load_job(job_id)
    if job is None:
        _flash(request, "Job not found.", "error")
        return RedirectResponse("/", status_code=303)
    summary = ""
    if job.summary_path and Path(job.summary_path).is_file():
        summary = Path(job.summary_path).read_text(encoding="utf-8", errors="replace")[-8000:]
    return render(request, "job.html", job=job, summary=summary)


@app.get("/settings", response_class=HTMLResponse)
async def settings_form(request: Request):
    return render(request, "settings.html", config=load_config())


@app.post("/settings")
async def settings_save(
    request: Request,
    destination_root: Annotated[str, Form()] = "",
    naming_template: Annotated[str, Form()] = "{nickname}_{date}_{time}",
    unknown_card_policy: Annotated[str, Form()] = UNKNOWN_HOLD,
    source_mode: Annotated[str, Form()] = SOURCE_ENTIRE,
    require_destination_mount: Annotated[str, Form()] = "",
    auto_unmount: Annotated[str, Form()] = "",
    verify_checksum: Annotated[str, Form()] = "",
    owner: Annotated[str, Form()] = "",
    group: Annotated[str, Form()] = "",
    dir_mode: Annotated[str, Form()] = "2775",
    file_mode: Annotated[str, Form()] = "0664",
    mount_wait_seconds: Annotated[int, Form()] = 60,
    log_dir: Annotated[str, Form()] = "/var/log/sdcopy",
    listen_host: Annotated[str, Form()] = "127.0.0.1",
    listen_port: Annotated[int, Form()] = 8743,
    listen_token: Annotated[str, Form()] = "",
    email_enabled: Annotated[str, Form()] = "",
    email_to: Annotated[str, Form()] = "",
    msmtp_account: Annotated[str, Form()] = "default",
):
    config = load_config()
    dest = destination_root.strip()
    if dest:
        dest_path = Path(dest).expanduser()
        if not dest_path.is_absolute():
            _flash(request, "destination must be an absolute path", "error")
            return RedirectResponse("/settings", status_code=303)
        if not dest_path.exists() or not dest_path.is_dir():
            _flash(request, f"destination does not exist: {dest_path}", "error")
            return RedirectResponse("/settings", status_code=303)
        if require_destination_mount == "on":
            from sdcopy.device import destination_mount_ok

            ok, mount_reason = destination_mount_ok(str(dest_path), require_mount=True)
            if not ok:
                _flash(request, mount_reason, "error")
                return RedirectResponse("/settings", status_code=303)
        dest = str(dest_path)
    if unknown_card_policy not in {UNKNOWN_HOLD, UNKNOWN_COPY}:
        unknown_card_policy = UNKNOWN_HOLD
    if not listen_is_loopback(listen_host.strip()) and not listen_token.strip() and not config.listen.token:
        _flash(request, "A token is required before listening beyond localhost.", "error")
        return RedirectResponse("/settings", status_code=303)
    config.destination_root = dest
    config.naming_template = naming_template.strip() or "{nickname}_{date}_{time}"
    config.unknown_card_policy = unknown_card_policy
    config.source_mode = source_mode if source_mode in {SOURCE_ENTIRE, SOURCE_DCIM} else SOURCE_ENTIRE
    config.require_destination_mount = require_destination_mount == "on"
    config.auto_unmount = auto_unmount == "on"
    config.verify_checksum = verify_checksum == "on"
    config.owner = owner.strip()
    config.group = group.strip()
    config.dir_mode = dir_mode.strip() or "2775"
    config.file_mode = file_mode.strip() or "0664"
    config.mount_wait_seconds = int(mount_wait_seconds)
    config.log_dir = log_dir.strip() or config.log_dir
    config.listen.host = listen_host.strip() or "127.0.0.1"
    config.listen.port = int(listen_port)
    if listen_token.strip():
        config.listen.token = listen_token.strip()
    config.email.enabled = email_enabled == "on"
    config.email.to = email_to.strip()
    config.email.msmtp_account = msmtp_account.strip() or "default"
    save_config(config)
    _flash(request, "Settings saved. A listen-address change needs a UI restart.")
    return RedirectResponse("/settings", status_code=303)


def run_server(host: str = "127.0.0.1", port: int = 8743) -> None:
    import uvicorn

    config = load_config()
    if not listen_is_loopback(host) and not config.listen.token:
        raise SystemExit("Refusing to bind a non-loopback address without listen.token")
    uvicorn.run("sdcopy.web.app:app", host=host, port=port, reload=False)
