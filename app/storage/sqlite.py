from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from app.models import GatewaySnapshot, GatewayConfig

_DB_PATH = Path(__file__).parent.parent.parent / "watchtower.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    schema = _SCHEMA_PATH.read_text()
    with get_connection() as conn:
        conn.executescript(schema)


def upsert_gateways(gateways: list[GatewayConfig]) -> None:
    with get_connection() as conn:
        for gw in gateways:
            conn.execute(
                """
                INSERT INTO gateways (name, host, ssh_login, enabled, country, profile)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(host) DO UPDATE SET
                    name=excluded.name,
                    ssh_login=excluded.ssh_login,
                    enabled=excluded.enabled,
                    country=excluded.country,
                    profile=excluded.profile
                """,
                (gw.name, gw.host, gw.ssh_login, int(gw.enabled), gw.country, gw.profile),
            )


def save_snapshot(snapshot: GatewaySnapshot) -> None:
    payload = snapshot.model_dump_json()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO snapshots
                (gateway_host, timestamp, overall_status, health_score,
                 ssh_status, docker_status, postgres_status, pipeline_status,
                 hardware_status, mirth_status, payload_json, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.gateway_host,
                snapshot.timestamp,
                snapshot.overall_status.value,
                snapshot.health_score,
                snapshot.ssh_status.value,
                snapshot.docker_status.value,
                snapshot.postgres_status.value,
                snapshot.pipeline_status.value,
                snapshot.hardware_status.value,
                snapshot.mirth_status.value,
                payload,
                snapshot.error_message,
            ),
        )


def get_latest_snapshot(host: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE gateway_host = ? ORDER BY timestamp DESC LIMIT 1",
            (host,),
        ).fetchone()
    return dict(row) if row else None


def get_latest_all() -> dict[str, dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.* FROM snapshots s
            INNER JOIN (
                SELECT gateway_host, MAX(timestamp) AS max_ts
                FROM snapshots GROUP BY gateway_host
            ) latest ON s.gateway_host = latest.gateway_host AND s.timestamp = latest.max_ts
            """
        ).fetchall()
    return {row["gateway_host"]: dict(row) for row in rows}


def get_history(host: str, limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE gateway_host = ? ORDER BY timestamp DESC LIMIT ?",
            (host, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def purge_old_snapshots(keep_days: int = 7) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM snapshots WHERE timestamp < datetime('now', ?)",
            (f"-{keep_days} days",),
        )
