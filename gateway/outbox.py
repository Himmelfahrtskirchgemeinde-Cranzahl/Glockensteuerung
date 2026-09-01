"""
Postausgang: Nachrichten verschicken, die die Extension eingestellt hat.

Warum dieser Umweg? Die Extension laeuft im Browser und kann keine E-Mail
senden - JavaScript spricht nur HTTP und WebSockets, SMTP ist ein eigenes
Protokoll auf TCP-Ebene. Und selbst wenn es ginge: Das Bundle kann jeder lesen,
der das Modul oeffnet; ein Postausgangs-Passwort darin waere oeffentlich.

Also legt die Extension ihre Nachrichten unter dem Schluessel 'outbox' in der
Kategorie 'steuerung' ab, und dieser Dienst holt sie beim naechsten Durchlauf
und verschickt sie. Danach leert er den Ausgang wieder.

Das Passwort bleibt dabei, wo es hingehoert: in der Kategorie 'email', die nur
Verwalter lesen duerfen, oder in der .env auf dem Server.
"""
from __future__ import annotations
import json
import logging

log = logging.getLogger("voco-gateway")

from kv import schluessel_von

VALUE_KEY = "outbox"


def _data_of(v: dict):
    raw = v.get("value")
    if isinstance(raw, str):
        try:
            return json.loads(raw).get("data")
        except Exception:
            return None
    if isinstance(raw, dict):
        return raw.get("data")
    return v.get("data")


def verarbeiten(ct, cfg, notifier) -> int:
    """Holt den Postausgang, verschickt alles darin und leert ihn.

    Gibt die Anzahl verschickter Nachrichten zurueck. Wirft NIE - ein klemmender
    Postausgang darf den Laeutebetrieb nicht anhalten.
    """
    if cfg.module_id is None or cfg.steuerung_cat_id is None:
        return 0
    if not notifier.enabled:
        return 0  # ohne Postausgang gaebe es nichts zu tun

    basis = (f"/custommodules/{cfg.module_id}"
             f"/customdatacategories/{cfg.steuerung_cat_id}/customdatavalues")
    try:
        werte = ct.get(basis) or []
    except Exception:
        return 0  # kein Leserecht o. Ae.

    eintrag = next((v for v in werte if schluessel_von(v) == VALUE_KEY), None)
    if not eintrag:
        return 0
    jobs = _data_of(eintrag)
    if not isinstance(jobs, list) or not jobs:
        return 0

    gesendet = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        betreff = str(job.get("subject") or "Nachricht aus der Glockensteuerung")
        text = str(job.get("body") or "")
        # dedup_key je Nachricht, sonst greift die Spam-Sperre des Notifiers und
        # verschluckt zwei Rueckmeldungen mit gleichem Betreff.
        if notifier.notify(betreff, text, dedup_key=f"outbox:{job.get('id')}"):
            gesendet += 1

    # Ausgang leeren - auch wenn einzelne Nachrichten nicht rausgingen. Sonst
    # versucht es der Dienst alle 20 Sekunden erneut und flutet das Postfach,
    # sobald es doch klappt. Fehlgeschlagene stehen im Log.
    try:
        ct.put(f"{basis}/{eintrag['id']}",
               {"value": json.dumps({"key": VALUE_KEY, "data": []})})
    except Exception as e:
        log.warning("Postausgang konnte nicht geleert werden: %s", e)

    if gesendet:
        log.info("%d Nachricht(en) aus dem Postausgang verschickt.", gesendet)
    return gesendet
