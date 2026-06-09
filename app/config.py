from __future__ import annotations
import yaml
from pathlib import Path
from app.models import GatewayConfig, AppConfig

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "gateways.yaml"


def load_config() -> tuple[AppConfig, list[GatewayConfig]]:
    with open(_CONFIG_PATH) as f:
        raw = yaml.safe_load(f)

    app_cfg = AppConfig(**(raw.get("app") or {}))
    gateways = [
        GatewayConfig(**gw)
        for gw in raw.get("gateways", [])
        if gw.get("enabled", True)
    ]
    return app_cfg, gateways
