from __future__ import annotations
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_cfg, gateways = load_config()

    db.init_db()
    db.upsert_gateways(gateways)

    teleport = TeleportAdapter(
        connection_timeout=app_cfg.ssh_connection_timeout,
        command_timeout=app_cfg.remote_command_timeout,
    )

    scheduler = Scheduler(gateways, app_cfg.check_interval_seconds, teleport)
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
    return app
