from __future__ import annotations
import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import load_config
from app.teleport.adapter import TeleportAdapter
from app.scheduler.runner import Scheduler
from app.storage import sqlite as db
from app.web import routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("watchtower")

_STATIC_DIR = Path(__file__).parent.parent / "static"


def _static_version() -> str:
    files = sorted(_STATIC_DIR.rglob("*") )
    h = hashlib.md5()
    for f in files:
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_cfg, gateways = load_config()

    db.init_db()
    db.upsert_gateways(gateways)

    teleport = TeleportAdapter(
        connection_timeout=app_cfg.ssh_connection_timeout,
        command_timeout=app_cfg.remote_command_timeout,
    )

    scheduler = Scheduler(gateways, app_cfg.check_interval_seconds, teleport, app_cfg.gateway_max_timeout)
    routes.init(gateways, teleport, scheduler)

    scheduler.start()
    logger.info("Watchtower running — %d gateways loaded", len(gateways))

    yield

    scheduler.stop()
    logger.info("Watchtower stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Watchtower", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(routes.router)

    version = _static_version()
    from app.web.routes import templates
    templates.env.globals["static_version"] = version
    logger.info("Static version: %s", version)

    return app
