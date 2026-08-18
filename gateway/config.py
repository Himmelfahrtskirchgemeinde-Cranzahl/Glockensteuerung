"""
Laedt die Gateway-Konfiguration.

Geraet + Regeln kommen aus DEMSELBEN ChurchTools-Custom-Module wie die
Extension (Modul-Shorty 'glockensteuerung', Kategorie 'settings'). So ist die
Konfiguration eine einzige Quelle der Wahrheit. Fallback: Geraet aus .env.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field

EXT_KEY = os.environ.get("VOCO_EXT_KEY", "glockensteuerung")


@dataclass
class DeviceConfig:
    serial: str
    device_pw: str
    broker_url: str = "wss://hew-voco.de:8084/mqtt"


@dataclass
class Rule:
    id: str
    name: str
    calendar_id: int | None
    category: str | None
    pgs_name: str
    lead_minutes: int
    active: bool


@dataclass
class GatewayConfig:
    device: DeviceConfig | None
    rules: list[Rule] = field(default_factory=list)


def _find_module(ct) -> dict | None:
    for m in ct.get("/custommodules"):
        if m.get("shorty") == EXT_KEY:
            return m
    return None


def load_from_churchtools(ct) -> GatewayConfig:
    """Liest Geraet + Regeln aus dem Custom-Module (von der Extension gepflegt)."""
    device = None
    rules: list[Rule] = []
    mod = _find_module(ct)
    if mod:
        mid = mod["id"]
        cats = ct.get(f"/custommodules/{mid}/customdatacategories")
        cat = next((c for c in cats if c.get("shorty") == "settings"), None)
        if cat:
            values = ct.get(f"/custommodules/{mid}/customdatacategories/{cat['id']}/customdatavalues")
            for v in values:
                data = _parse_value(v.get("value"))
                if not isinstance(data, dict):
                    continue
                if data.get("key") == "device" and isinstance(data.get("data"), dict):
                    d = data["data"]
                    if d.get("serial") and d.get("devicePw"):
                        device = DeviceConfig(d["serial"], d["devicePw"],
                                              d.get("brokerUrl") or "wss://hew-voco.de:8084/mqtt")
                elif data.get("key") == "rules" and isinstance(data.get("data"), list):
                    for r in data["data"]:
                        rules.append(Rule(
                            id=str(r.get("id", "")),
                            name=r.get("name", "Regel"),
                            calendar_id=r.get("calendarId"),
                            category=r.get("category"),
                            pgs_name=r.get("pgsName", ""),
                            lead_minutes=int(r.get("leadMinutes", 0) or 0),
                            active=bool(r.get("active", True)),
                        ))
    # Fallback Geraet aus .env
    if device is None and os.environ.get("VOCO_SERIAL") and os.environ.get("VOCO_DEVICE_PW"):
        device = DeviceConfig(os.environ["VOCO_SERIAL"], os.environ["VOCO_DEVICE_PW"],
                              os.environ.get("VOCO_BROKER_URL", "wss://hew-voco.de:8084/mqtt"))
    return GatewayConfig(device=device, rules=rules)


def _parse_value(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def load_dotenv(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
