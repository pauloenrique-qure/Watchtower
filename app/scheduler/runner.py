from __future__ import annotations
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.models import (
    GatewayConfig, GatewaySnapshot, SchedulerState,
    Status, HardwareResult, DockerResult, PostgresResult, PipelineResult, MirthResult,
)
from app.teleport.adapter import TeleportAdapter, SessionExpiredError, TeleportError
from app.checks import hardware, docker, postgres, pipeline, mirth
from app.health import compute_score, compute_overall_status
from app.storage import sqlite as db

logger = logging.getLogger("watchtower.scheduler")


_FLAP_THRESHOLD = 2  # consecutive SSH failures before marking CRITICAL


class Scheduler:
    def __init__(self, gateways: list[GatewayConfig], interval_seconds: int, teleport: TeleportAdapter):
        self._gateways = gateways
        self._interval = interval_seconds
        self._teleport = teleport
        self._state = SchedulerState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._failure_counts: dict[str, int] = {}
        self._counts_lock = threading.Lock()

    @property
    def state(self) -> SchedulerState:
        return self._state

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        logger.info("Scheduler stopped")

    def pause(self) -> None:
        self._state.running = False
        logger.info("Scheduler paused")

    def resume(self) -> None:
        self._state.running = True
        logger.info("Scheduler resumed")

    def trigger_now(self) -> None:
        if self._state.in_progress:
            return
        t = threading.Thread(target=self._run_checks, daemon=True)
        t.start()

    def set_interval(self, seconds: int) -> None:
        self._interval = seconds

    def _loop(self) -> None:
        self._run_checks()
        while not self._stop_event.is_set():
            next_run = time.time() + self._interval
            self._state.next_run = datetime.fromtimestamp(next_run, tz=timezone.utc).isoformat()

            while time.time() < next_run:
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            if self._state.running:
                self._run_checks()

    def _run_checks(self) -> None:
        with self._lock:
            if self._state.in_progress:
                return
            self._state.in_progress = True

        try:
            tsh = self._teleport.status()
            if not tsh["active"]:
                logger.warning("Teleport session expired — skipping checks")
                self._state.in_progress = False
                return

            with ThreadPoolExecutor(max_workers=len(self._gateways)) as pool:
                futures = {pool.submit(self._check_and_save, gw): gw for gw in self._gateways}
                for future in as_completed(futures):
                    exc = future.exception()
                    if exc:
                        logger.error("Unexpected error checking %s: %s", futures[future].name, exc)

            self._state.last_run = datetime.now(tz=timezone.utc).isoformat()
        finally:
            self._state.in_progress = False

    def _check_and_save(self, gw: GatewayConfig) -> None:
        snapshot = _check_gateway(gw, self._teleport)
        if snapshot.ssh_status == Status.CRITICAL:
            with self._counts_lock:
                self._failure_counts[gw.host] = self._failure_counts.get(gw.host, 0) + 1
                count = self._failure_counts[gw.host]
            if count < _FLAP_THRESHOLD:
                logger.warning(
                    "Gateway %s SSH failure #%d/%d — suppressed (flap protection)",
                    gw.name, count, _FLAP_THRESHOLD,
                )
                return
        else:
            with self._counts_lock:
                self._failure_counts[gw.host] = 0
        db.save_snapshot(snapshot)
        logger.info("Gateway %s → %s (score=%d)", gw.name, snapshot.overall_status, snapshot.health_score)


def _check_gateway(gw: GatewayConfig, teleport: TeleportAdapter) -> GatewaySnapshot:
    now = datetime.now(tz=timezone.utc).isoformat()
    ssh_status = Status.UNKNOWN
    hw: HardwareResult | None = None
    dk: DockerResult | None = None
    pg: PostgresResult | None = None
    pl: PipelineResult | None = None
    mth: MirthResult | None = None
    error_msg = ""

    try:
        teleport.ssh(gw.host, gw.ssh_login, "hostname", timeout=15)
        ssh_status = Status.OK
    except SessionExpiredError as e:
        error_msg = f"Teleport session expired: {e}"
        return _skipped_snapshot(gw, now, error_msg)
    except TeleportError as e:
        error_msg = str(e)
        return _failed_snapshot(gw, now, error_msg)

    hw = hardware.run(gw, teleport)
    dk = docker.run(gw, teleport)
    mth = mirth.run(dk)

    if dk.status != Status.CRITICAL or dk.core_status != Status.CRITICAL:
        pg = postgres.run(gw, teleport)

    if pg and pg.reachable:
        pl = pipeline.run(gw, teleport)
    else:
        pl = PipelineResult(status=Status.SKIPPED)

    mirth_present = mth.present if mth else False
    score = compute_score(ssh_status, dk, pg, pl, hw, mirth_present)

    snapshot = GatewaySnapshot(
        gateway_host=gw.host,
        gateway_name=gw.name,
        timestamp=now,
        overall_status=Status.UNKNOWN,
        health_score=score,
        ssh_status=ssh_status,
        docker_status=dk.status if dk else Status.UNKNOWN,
        postgres_status=pg.status if pg else Status.SKIPPED,
        pipeline_status=pl.status if pl else Status.SKIPPED,
        hardware_status=hw.status if hw else Status.UNKNOWN,
        mirth_status=mth.status if mth else Status.UNKNOWN,
        hardware=hw,
        docker=dk,
        postgres=pg,
        pipeline=pl,
        mirth=mth,
        error_message=error_msg,
    )
    snapshot.overall_status = compute_overall_status(snapshot)
    return snapshot


def _failed_snapshot(gw: GatewayConfig, timestamp: str, error: str) -> GatewaySnapshot:
    return GatewaySnapshot(
        gateway_host=gw.host,
        gateway_name=gw.name,
        timestamp=timestamp,
        overall_status=Status.CRITICAL,
        health_score=0,
        ssh_status=Status.CRITICAL,
        docker_status=Status.SKIPPED,
        postgres_status=Status.SKIPPED,
        pipeline_status=Status.SKIPPED,
        hardware_status=Status.SKIPPED,
        mirth_status=Status.UNKNOWN,
        error_message=error,
    )


def _skipped_snapshot(gw: GatewayConfig, timestamp: str, error: str) -> GatewaySnapshot:
    return GatewaySnapshot(
        gateway_host=gw.host,
        gateway_name=gw.name,
        timestamp=timestamp,
        overall_status=Status.UNKNOWN,
        health_score=0,
        ssh_status=Status.UNKNOWN,
        docker_status=Status.SKIPPED,
        postgres_status=Status.SKIPPED,
        pipeline_status=Status.SKIPPED,
        hardware_status=Status.SKIPPED,
        mirth_status=Status.UNKNOWN,
        error_message=error,
    )
