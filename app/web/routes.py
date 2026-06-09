from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.models import GatewayConfig, Status
from app.teleport.adapter import TeleportAdapter
from app.storage import sqlite as db

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()

# Injected by main.py
_gateways: list[GatewayConfig] = []
_teleport: TeleportAdapter | None = None
_scheduler = None


def init(gateways: list[GatewayConfig], teleport: TeleportAdapter, scheduler) -> None:
    global _gateways, _teleport, _scheduler
    _gateways = gateways
    _teleport = teleport
    _scheduler = scheduler


# ──────────────────────────── HTML routes ─────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    tsh = _teleport.status()
    latest = db.get_latest_all()
    sched = _scheduler.state if _scheduler else None

    gateway_data = []
    for gw in _gateways:
        row = latest.get(gw.host)
        snapshot = _enrich_snapshot(row, gw)
        gateway_data.append(snapshot)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "gateways": gateway_data,
        "teleport_active": tsh["active"],
        "scheduler": sched,
    })


@router.get("/gateway/{host:path}", response_class=HTMLResponse)
async def gateway_detail(request: Request, host: str):
    gw = _find_gateway(host)
    row = db.get_latest_snapshot(host)
    history = db.get_history(host, limit=50)
    snapshot = _enrich_snapshot(row, gw) if gw else {}

    return templates.TemplateResponse("gateway_detail.html", {
        "request": request,
        "gw": gw,
        "snapshot": snapshot,
        "history": history,
    })


# ──────────────────────────── JSON API ────────────────────────────────

@router.get("/api/status")
async def api_status():
    tsh = _teleport.status()
    latest = db.get_latest_all()
    sched = _scheduler.state if _scheduler else None

    result = []
    for gw in _gateways:
        row = latest.get(gw.host)
        result.append(_enrich_snapshot(row, gw))

    return JSONResponse({
        "teleport_active": tsh["active"],
        "scheduler": sched.model_dump() if sched else {},
        "gateways": result,
    })


@router.get("/api/gateway/{host:path}")
async def api_gateway(host: str):
    row = db.get_latest_snapshot(host)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    payload = json.loads(row.get("payload_json", "{}"))
    return JSONResponse(payload)


@router.get("/api/history/{host:path}")
async def api_history(host: str):
    history = db.get_history(host, limit=50)
    return JSONResponse([
        {
            "timestamp": r["timestamp"],
            "overall_status": r["overall_status"],
            "health_score": r["health_score"],
            "ssh_status": r["ssh_status"],
        }
        for r in history
    ])


@router.get("/api/teleport/status")
async def api_teleport_status():
    tsh = _teleport.status()
    return JSONResponse({"active": tsh["active"], "output": tsh["output"]})


# ──────────────────────────── Scheduler control ───────────────────────

@router.post("/api/scheduler/trigger")
async def scheduler_trigger():
    if _scheduler:
        _scheduler.trigger_now()
    return JSONResponse({"ok": True})


@router.post("/api/scheduler/pause")
async def scheduler_pause():
    if _scheduler:
        _scheduler.pause()
    return JSONResponse({"ok": True})


@router.post("/api/scheduler/resume")
async def scheduler_resume():
    if _scheduler:
        _scheduler.resume()
    return JSONResponse({"ok": True})


# ──────────────────────────── Helpers ─────────────────────────────────

def _find_gateway(host: str) -> GatewayConfig | None:
    return next((g for g in _gateways if g.host == host), None)


def _enrich_snapshot(row: dict | None, gw: GatewayConfig | None) -> dict:
    if row is None:
        return {
            "name": gw.name if gw else "Unknown",
            "host": gw.host if gw else "",
            "profile": gw.profile if gw else "",
            "overall_status": "UNKNOWN",
            "health_score": None,
            "ssh_status": "UNKNOWN",
            "docker_status": "UNKNOWN",
            "postgres_status": "UNKNOWN",
            "pipeline_status": "UNKNOWN",
            "hardware_status": "UNKNOWN",
            "mirth_status": "UNKNOWN",
            "timestamp": None,
            "error_message": "",
            "uptime_short": "",
            "payload": {},
        }

    payload = json.loads(row.get("payload_json", "{}"))
    hw = payload.get("hardware") or {}
    return {
        "name": gw.name if gw else row["gateway_host"],
        "host": row["gateway_host"],
        "profile": gw.profile if gw else "",
        "overall_status": row["overall_status"],
        "health_score": row["health_score"],
        "ssh_status": row["ssh_status"],
        "docker_status": row["docker_status"],
        "postgres_status": row["postgres_status"],
        "pipeline_status": row["pipeline_status"],
        "hardware_status": row["hardware_status"],
        "mirth_status": row["mirth_status"],
        "timestamp": row["timestamp"],
        "error_message": row.get("error_message", ""),
        "uptime_short": hw.get("uptime_short", ""),
        "payload": payload,
    }
