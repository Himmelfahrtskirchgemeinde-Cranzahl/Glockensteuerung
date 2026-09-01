"""
Laedt die Gateway-Konfiguration.

Geraet + Regeln kommen aus DEMSELBEN ChurchTools-Custom-Module wie die
Extension (Modul-Shorty 'glockensteuerung'). So ist die Konfiguration eine
einzige Quelle der Wahrheit. Fallback: Geraet aus .env.

Die Extension legt pro Untermenue eine eigene Kategorie an ('steuerung' fuer das
Geraet, 'regeln' fuer die Regeln), damit sich Rechte je Untermenue vergeben
lassen. Deshalb werden hier ALLE Kategorien des Moduls nach den Schluesseln
'device' und 'rules' durchsucht – nicht mehr nur die alte Kategorie 'settings'.
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
    # Nur Termine mit GENAU diesem Titel. Verglichen wird der Termin-Titel, nicht
    # mehr die Veranstaltungsart: Die haengt an einer verknuepften Veranstaltung
    # und ist in der Praxis nicht gepflegt, wodurch solche Regeln nie griffen.
    title: str | None
    pgs_name: str
    lead_minutes: int
    active: bool


@dataclass
class EmailConfig:
    """Zugang zum Postausgang, gepflegt in der Extension (Kategorie 'email').

    Die Extension kann selbst keine E-Mail verschicken - ein Browser spricht kein
    SMTP. Sie hinterlegt hier nur die Zugangsdaten; verschickt wird vom Gateway.
    """
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    mail_from: str = ""
    mail_to: str = ""
    security: str = "starttls"      # 'starttls' (Port 587) oder 'ssl' (Port 465)
    send_feedback: bool = True
    send_errors: bool = True


@dataclass
class GatewayConfig:
    device: DeviceConfig | None
    rules: list[Rule] = field(default_factory=list)
    email: EmailConfig | None = None
    """Modul-ID und Kategorie-ID von 'steuerung' - fuer den Postausgang."""
    module_id: int | None = None
    steuerung_cat_id: int | None = None


def _find_module(ct) -> dict | None:
    for m in ct.get("/custommodules"):
        if m.get("shorty") == EXT_KEY:
            return m
    return None


# Vorrang der Kategorien beim Suchen. Die Extension legt heute 'steuerung'
# (Geraet) und 'regeln' (Regeln) an; 'settings' und 'geraet' sind Altbestand und
# werden weiter gelesen, damit alte Installationen nicht brechen.
_DEVICE_CAT_ORDER = ("steuerung", "settings", "geraet")
_RULES_CAT_ORDER = ("regeln", "settings")


def _to_rule(r: dict) -> Rule:
    return Rule(
        id=str(r.get("id", "")),
        name=r.get("name", "Regel"),
        calendar_id=r.get("calendarId"),
        # 'category' ist das Altfeld (Veranstaltungsart) – der dort eingetragene
        # Text wird als Termin-Titel weiterverwendet, damit alte Regeln greifen.
        title=r.get("title") or r.get("category") or None,
        pgs_name=r.get("pgsName", ""),
        lead_minutes=int(r.get("leadMinutes", 0) or 0),
        active=bool(r.get("active", True)),
    )


def load_from_churchtools(ct) -> GatewayConfig:
    """Liest Geraet + Regeln aus dem Custom-Module (von der Extension gepflegt).

    Durchsucht ALLE Kategorien des Moduls nach den Schluesseln 'device' und
    'rules'. Frueher wurde nur die Kategorie 'settings' gelesen – die legt die
    Extension seit der Rechte-Umstellung aber nicht mehr an, wodurch der Gateway
    dauerhaft 0 Regeln sah und nie automatisch ausgeloest hat.
    """
    device = None
    rules: list[Rule] = []
    email = None
    module_id = None
    steuerung_cat_id = None
    devices_by_cat: dict[str, DeviceConfig] = {}
    rules_by_cat: dict[str, list[Rule]] = {}

    mod = _find_module(ct)
    if mod:
        mid = module_id = mod["id"]
        try:
            cats = ct.get(f"/custommodules/{mid}/customdatacategories")
        except Exception:
            cats = []
        for cat in cats or []:
            shorty = cat.get("shorty") or ""
            if shorty == "steuerung":
                steuerung_cat_id = cat.get("id")
            try:
                values = ct.get(
                    f"/custommodules/{mid}/customdatacategories/{cat['id']}/customdatavalues"
                )
            except Exception:
                continue  # keine Leseberechtigung o. Ae. -> naechste Kategorie
            for v in values or []:
                data = _parse_value(v.get("value"))
                if not isinstance(data, dict):
                    continue
                key, payload = data.get("key"), data.get("data")
                if key == "device" and isinstance(payload, dict):
                    if payload.get("serial") and payload.get("devicePw"):
                        devices_by_cat[shorty] = DeviceConfig(
                            payload["serial"], payload["devicePw"],
                            payload.get("brokerUrl") or "wss://hew-voco.de:8084/mqtt")
                elif key == "rules" and isinstance(payload, list):
                    rules_by_cat[shorty] = [_to_rule(r) for r in payload if isinstance(r, dict)]
                elif key == "email" and isinstance(payload, dict):
                    email = _to_email(payload)

    # Aktuelle Kategorie gewinnt, sonst irgendeine gefundene.
    for shorty in _DEVICE_CAT_ORDER:
        if shorty in devices_by_cat:
            device = devices_by_cat[shorty]
            break
    else:
        device = next(iter(devices_by_cat.values()), None)

    for shorty in _RULES_CAT_ORDER:
        if shorty in rules_by_cat:
            rules = rules_by_cat[shorty]
            break
    else:
        rules = next(iter(rules_by_cat.values()), [])

    # Fallback Geraet aus .env
    if device is None and os.environ.get("VOCO_SERIAL") and os.environ.get("VOCO_DEVICE_PW"):
        device = DeviceConfig(os.environ["VOCO_SERIAL"], os.environ["VOCO_DEVICE_PW"],
                              os.environ.get("VOCO_BROKER_URL", "wss://hew-voco.de:8084/mqtt"))

    # Fallback Postausgang aus .env. Die Extension hat Vorrang, damit sich die
    # Zugangsdaten ohne Zugriff auf den Server aendern lassen.
    if email is None and os.environ.get("SMTP_HOST"):
        email = EmailConfig(
            host=os.environ["SMTP_HOST"].strip(),
            port=int(os.environ.get("SMTP_PORT", "587") or 587),
            user=os.environ.get("SMTP_USER", "").strip(),
            password=os.environ.get("SMTP_PASS", ""),
            mail_from=os.environ.get("EMAIL_FROM", "").strip(),
            mail_to=os.environ.get("EMAIL_TO", "").strip(),
            security="ssl" if os.environ.get("SMTP_SSL", "").strip().lower() in ("1", "true", "yes")
                     else "starttls",
        )

    return GatewayConfig(device=device, rules=rules, email=email,
                         module_id=module_id, steuerung_cat_id=steuerung_cat_id)


def _to_email(d: dict) -> EmailConfig:
    return EmailConfig(
        host=str(d.get("host") or "").strip(),
        port=int(d.get("port") or 587),
        user=str(d.get("user") or "").strip(),
        password=str(d.get("password") or ""),
        mail_from=str(d.get("from") or "").strip(),
        mail_to=str(d.get("to") or "").strip(),
        security=str(d.get("security") or "starttls"),
        send_feedback=bool(d.get("sendFeedback", True)),
        send_errors=bool(d.get("sendErrors", True)),
    )


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
