#!/usr/bin/env python3
"""
Gateway-Dienst: loest automatisch das passende VOCO-Laeuteprogramm zur
ChurchTools-Termin-Zeit aus.

Ablauf:
  - Konfiguration (Geraet + Regeln) aus ChurchTools laden (von der Extension gepflegt)
  - kommende Termine holen, per Regeln (Kalender + exakter Titel) auf PGS abbilden
  - zum Zeitpunkt (Start - Vorlauf) 'START:<PGS>:INSTANT' per MQTT senden
  - bereits ausgeloeste Termine werden gemerkt (state.json), kein Doppel-Laeuten

Start:  python scheduler.py         (laeuft dauerhaft)
        python scheduler.py --dry-run   (plant, loest aber NICHT aus)
Konfig ueber .env:  CT_BASE_URL, CT_LOGIN_TOKEN  (+ optional VOCO_* Fallback)
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import os
import time

from churchtools import ChurchTools
from config import GatewayConfig, Rule, load_dotenv, load_from_churchtools
from notify import EmailNotifier
from voco_mqtt import Voco, decode_name

STATE_FILE = os.environ.get("VOCO_STATE_FILE", "state.json")
HORIZON_HOURS = 26          # so weit im Voraus planen
CONFIG_REFRESH_S = 300      # Konfig/Termine alle 5 min neu laden
TICK_S = 20                 # so oft pruefen, ob etwas ansteht
FIRE_WINDOW_S = 150         # Toleranz: bis 2,5 min nach Soll noch ausloesen

log = logging.getLogger("voco-gateway")


def load_state() -> set[str]:
    try:
        return set(json.load(open(STATE_FILE)))
    except Exception:
        return set()


def save_state(fired: set[str]):
    # nur die letzten ~500 Eintraege behalten
    try:
        json.dump(sorted(fired)[-500:], open(STATE_FILE, "w"))
    except Exception as e:
        log.warning("state speichern fehlgeschlagen: %s", e)


def quiet_now() -> bool:
    """Optionale Ruhezeit VOCO_QUIET='22:00-06:00' -> in dem Fenster nie ausloesen."""
    q = os.environ.get("VOCO_QUIET", "").strip()
    if not q or "-" not in q:
        return False
    try:
        a, b = q.split("-")
        now = dt.datetime.now().time()
        start = dt.time.fromisoformat(a)
        end = dt.time.fromisoformat(b)
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end   # ueber Mitternacht
    except Exception:
        return False


def rule_matches(rule: Rule, occ: dict) -> bool:
    """Passt die Regel auf dieses Termin-Vorkommen?

    Deckungsgleich mit der Vorschau in der Extension (App.vue,
    `loadNextRingings`) – sonst zeigt sie etwas anderes an, als real laeutet:
      - Regel OHNE Titel → jeder Termin der gewaehlten Kalender.
      - Regel MIT Titel  → nur Termine, deren Titel EXAKT uebereinstimmt.
        „Gottesdienst" trifft also NICHT auch „Festgottesdienst".
    """
    if not rule.active:
        return False
    if rule.calendar_id is not None and occ.get("calendarId") != rule.calendar_id:
        return False
    if rule.title:
        if (occ.get("title") or "").strip().lower() != rule.title.strip().lower():
            return False
    return True


def build_schedule(ct: ChurchTools, cfg: GatewayConfig) -> list[dict]:
    """Liefert Liste geplanter Ausloesungen: {ts, key, pgs_name, title}."""
    today = dt.date.today()
    # HORIZON_HOURS ab JETZT – spaet abends reicht ein Tag Aufschlag nicht,
    # deshalb grosszuegig bis uebermorgen holen und unten exakt filtern.
    to = today + dt.timedelta(days=HORIZON_HOURS // 24 + 2)

    active = [r for r in cfg.rules if r.active and r.pgs_name]
    if not active:
        log.warning("Keine aktive Regel mit Laeuteprogramm – es wird nichts geplant.")
        return []

    cal_ids = {r.calendar_id for r in active if r.calendar_id}
    # Eine Regel ohne Kalenderangabe gilt fuer ALLE Kalender – dann muessen auch
    # alle abgefragt werden. Frueher wurden nur die Kalender geholt, die andere
    # Regeln ausdruecklich nannten; gab es keine solche Regel, wurden gar keine
    # Termine abgerufen und es wurde nie ausgeloest.
    if any(r.calendar_id is None for r in active):
        try:
            cal_ids |= {c["id"] for c in ct.calendars() if c.get("id")}
        except Exception as e:
            log.error("Kalenderliste laden fehlgeschlagen: %s", e)
    occs = ct.appointments(sorted(cal_ids), today, to) if cal_ids else []

    now_ts = time.time()
    horizon_ts = now_ts + HORIZON_HOURS * 3600
    plan = []
    for occ in occs:
        start = occ.get("start")
        if not start:
            continue
        start_ts = start.timestamp()
        for rule in active:
            if not rule_matches(rule, occ):
                continue
            fire_ts = start_ts - rule.lead_minutes * 60
            if fire_ts < now_ts - FIRE_WINDOW_S or fire_ts > horizon_ts:
                continue
            plan.append({
                "ts": fire_ts,
                "key": f"{rule.id}:{occ['kind']}:{occ['id']}:{int(start_ts)}",
                "pgs_name": rule.pgs_name,
                "title": occ.get("title", ""),
            })
    plan.sort(key=lambda p: p["ts"])

    # Leerer Plan darf nie unerklaert bleiben – sonst sucht man den Fehler im
    # Nichts. Dieselbe Diagnose zeigt die Extension unter der leeren Vorschau.
    if not plan:
        gesucht = sorted({r.title.strip() for r in active if r.title})
        vorhanden = sorted({o["title"] for o in occs if o.get("title")})[:12]
        if not occs:
            log.warning("Keine Ausloesung geplant: im Zeitraum liegen keine Termine "
                        "in den Kalendern %s.", sorted(cal_ids) or "(keine)")
        elif gesucht:
            log.warning("Keine Ausloesung geplant: %d Termin(e) gefunden, aber kein Titel "
                        "passt exakt. Gesucht: %s – vorhanden: %s",
                        len(occs), ", ".join(gesucht), ", ".join(vorhanden) or "(ohne Titel)")
        else:
            log.warning("Keine Ausloesung geplant: %d Termin(e) gefunden, aber alle liegen "
                        "ausserhalb des Zeitfensters (%d h).", len(occs), HORIZON_HOURS)
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Plant, loest aber NICHT aus")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    # Simulation: per Flag ODER dauerhaft per .env (VOCO_SIMULATION=1) -> loest NICHT aus
    sim_env = os.environ.get("VOCO_SIMULATION", "").strip().lower() in ("1", "true", "yes", "on")
    dry = args.dry_run or sim_env

    # Automatische Fehler-E-Mails (an EMAIL_TO, Standard josua.hess@icloud.com)
    notifier = EmailNotifier()
    log.addHandler(notifier.log_handler())

    base = os.environ.get("CT_BASE_URL")
    token = os.environ.get("CT_LOGIN_TOKEN") or os.environ.get("CT_API_TOKEN")
    if not base or not token:
        raise SystemExit("CT_BASE_URL und CT_LOGIN_TOKEN in .env noetig")

    ct = ChurchTools(base, token)
    cfg = load_from_churchtools(ct)
    if not cfg.device:
        raise SystemExit("Kein Geraet konfiguriert (Extension oder .env: VOCO_SERIAL/VOCO_DEVICE_PW)")

    log.info("Geraet %s, %d Regel(n)%s", cfg.device.serial, len(cfg.rules),
             "  [SIMULATION – loest NICHT aus]" if dry else "")

    voco = Voco(serial=cfg.device.serial, device_pw=cfg.device.device_pw,
                broker_url=cfg.device.broker_url)
    try:
        voco.connect()
        voco.request_list()
    except Exception as e:
        log.error("Verbindung zur Steuerung (MQTT) fehlgeschlagen: %s", e)
        raise

    fired = load_state()
    plan: list[dict] = []
    last_refresh = 0.0

    try:
        while True:
            now = time.time()
            if now - last_refresh > CONFIG_REFRESH_S:
                try:
                    cfg = load_from_churchtools(ct)
                    plan = build_schedule(ct, cfg)
                    voco.request_list()
                    last_refresh = now
                    upcoming = [f"{time.strftime('%H:%M', time.localtime(p['ts']))} → {p['pgs_name']}" for p in plan[:5]]
                    log.info("Plan aktualisiert: %d Ausloesung(en). Naechste: %s",
                             len(plan), ", ".join(upcoming) or "keine")
                except Exception as e:
                    log.error("Konfig/Termine laden fehlgeschlagen: %s", e)

            for p in plan:
                if p["key"] in fired:
                    continue
                if now >= p["ts"] and now < p["ts"] + FIRE_WINDOW_S:
                    if quiet_now():
                        log.warning("Ruhezeit aktiv – ueberspringe %s (%s)", p["pgs_name"], p["title"])
                        fired.add(p["key"]); save_state(fired)
                        continue
                    raw = voco.resolve(p["pgs_name"]) or p["pgs_name"]
                    if dry:
                        log.info("[SIMULATION] wuerde ausloesen: %s (%s)", decode_name(raw), p["title"])
                    else:
                        try:
                            voco.start(raw)
                            log.info("AUSGELOEST: %s  (Termin: %s)", decode_name(raw), p["title"])
                        except Exception as e:
                            log.error("Ausloesen fehlgeschlagen: %s (%s): %s", decode_name(raw), p["title"], e)
                    fired.add(p["key"]); save_state(fired)

            time.sleep(TICK_S)
    except KeyboardInterrupt:
        pass
    finally:
        voco.close()


if __name__ == "__main__":
    main()
