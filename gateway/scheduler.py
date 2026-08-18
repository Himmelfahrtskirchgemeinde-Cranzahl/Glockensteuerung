#!/usr/bin/env python3
"""
Gateway-Dienst: loest automatisch das passende VOCO-Laeuteprogramm zur
ChurchTools-Termin-Zeit aus.

Ablauf:
  - Konfiguration (Geraet + Regeln) aus ChurchTools laden (von der Extension gepflegt)
  - kommende Termine/Veranstaltungen holen, per Regeln auf PGS abbilden
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
    if not rule.active:
        return False
    if rule.calendar_id is not None and occ.get("calendarId") != rule.calendar_id:
        return False
    if rule.category:
        if (occ.get("category") or "").strip().lower() != rule.category.strip().lower():
            return False
    return True


def build_schedule(ct: ChurchTools, cfg: GatewayConfig) -> list[dict]:
    """Liefert Liste geplanter Ausloesungen: {ts, key, pgs_name, title}."""
    today = dt.date.today()
    to = today + dt.timedelta(hours=HORIZON_HOURS) + dt.timedelta(days=1)
    cal_ids = sorted({r.calendar_id for r in cfg.rules if r.calendar_id})
    occs = []
    if cal_ids:
        occs += ct.appointments(cal_ids, today, to)
    if any(r.category for r in cfg.rules):
        occs += ct.events(today, to)

    now_ts = time.time()
    horizon_ts = now_ts + HORIZON_HOURS * 3600
    plan = []
    for occ in occs:
        start = occ.get("start")
        if not start:
            continue
        start_ts = start.timestamp()
        for rule in cfg.rules:
            if not rule.pgs_name or not rule_matches(rule, occ):
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
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Plant, loest aber NICHT aus")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    base = os.environ.get("CT_BASE_URL")
    token = os.environ.get("CT_LOGIN_TOKEN") or os.environ.get("CT_API_TOKEN")
    if not base or not token:
        raise SystemExit("CT_BASE_URL und CT_LOGIN_TOKEN in .env noetig")

    ct = ChurchTools(base, token)
    cfg = load_from_churchtools(ct)
    if not cfg.device:
        raise SystemExit("Kein Geraet konfiguriert (Extension oder .env: VOCO_SERIAL/VOCO_DEVICE_PW)")

    log.info("Geraet %s, %d Regel(n)%s", cfg.device.serial, len(cfg.rules),
             "  [DRY-RUN]" if args.dry_run else "")

    voco = Voco(serial=cfg.device.serial, device_pw=cfg.device.device_pw,
                broker_url=cfg.device.broker_url)
    voco.connect()
    voco.request_list()

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
                    log.warning("Konfig/Termine laden fehlgeschlagen: %s", e)

            for p in plan:
                if p["key"] in fired:
                    continue
                if now >= p["ts"] and now < p["ts"] + FIRE_WINDOW_S:
                    if quiet_now():
                        log.warning("Ruhezeit aktiv – ueberspringe %s (%s)", p["pgs_name"], p["title"])
                        fired.add(p["key"]); save_state(fired)
                        continue
                    raw = voco.resolve(p["pgs_name"]) or p["pgs_name"]
                    if args.dry_run:
                        log.info("[DRY-RUN] wuerde ausloesen: %s (%s)", decode_name(raw), p["title"])
                    else:
                        voco.start(raw)
                        log.info("AUSGELOEST: %s  (Termin: %s)", decode_name(raw), p["title"])
                    fired.add(p["key"]); save_state(fired)

            time.sleep(TICK_S)
    except KeyboardInterrupt:
        pass
    finally:
        voco.close()


if __name__ == "__main__":
    main()
