#!/usr/bin/env python3
"""
Gateway-Dienst: loest automatisch das passende VOCO-Laeuteprogramm zur
ChurchTools-Termin-Zeit aus.

Ablauf:
  - Konfiguration (Geraet + Regeln) aus ChurchTools laden (von der Extension gepflegt)
  - kommende Termine holen, per Regeln (Kalender + exakter Titel) auf PGS abbilden
  - zum Zeitpunkt (Start - Vorlauf) 'START:<PGS>:INSTANT' per MQTT senden
  - bereits ausgeloeste Termine werden gemerkt (state.json), kein Doppel-Laeuten
  - alle 2 min ein Lebenszeichen nach ChurchTools schreiben, damit die Extension
    warnen kann, wenn dieser Dienst nicht laeuft
  - den Postausgang der Extension abarbeiten (Feedback, Stoerungsmeldungen)

Der Dienst gibt nicht auf: Faellt das Netz aus, laeuft die ChurchTools-Sitzung
ab oder ist beim Hochfahren des Rechners noch keine Verbindung da, wartet er und
versucht es erneut - statt sich wie frueher zu beenden. Auf dem Rechner der
Gemeinde war genau das der Grund, warum er "im Taskmanager lief", aber nichts
tat: Der Prozess war laengst gestorben.

Start:  python scheduler.py         (laeuft dauerhaft)
        python scheduler.py --dry-run   (plant, loest aber NICHT aus)
Konfig ueber .env:  CT_BASE_URL, CT_LOGIN_TOKEN  (+ optional VOCO_* Fallback)
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import logging.handlers
import os
import threading
import time

from churchtools import ChurchTools
from config import EXT_KEY, GatewayConfig, Rule, load_dotenv, load_from_churchtools
from ereignisse import Ereignisse, Zustandswaechter
from heartbeat import Heartbeat, mask_serial
from notify import EmailNotifier
import outbox
import pfade
from voco_mqtt import Voco, decode_name

HORIZON_HOURS = 26          # so weit im Voraus planen
CONFIG_REFRESH_S = 300      # Konfig/Termine alle 5 min neu laden
TICK_S = 20                 # so oft pruefen, ob etwas ansteht
OUTBOX_S = 60               # so oft den Postausgang der Extension abarbeiten
FIRE_WINDOW_S = 150         # Toleranz: bis 2,5 min nach Soll noch ausloesen
HEARTBEAT_S = 120           # so oft ein Lebenszeichen nach ChurchTools schreiben

# Wiederanlauf nach einer Stoerung: erst kurz warten, dann immer laenger, aber
# hoechstens 5 Minuten. Kurz genug, dass ein Aussetzer beim Hochfahren keine
# Rolle spielt; lang genug, dass ein dauerhaft falscher Zugang nicht im
# Sekundentakt ins Protokoll schreibt.
WIEDERANLAUF_MIN_S = 15
WIEDERANLAUF_MAX_S = 300
# Ab wann ein Lauf als "hat getragen" gilt und die Wartezeit wieder von vorn
# beginnt.
GELUNGEN_AB_S = 600
# So lange darf die MQTT-Verbindung weg sein, bevor alles neu aufgebaut wird.
# paho verbindet selbst neu; hilft das nicht, liegt es meist tiefer (Rechner war
# im Standby, Zertifikatskontext veraltet) - dann hilft nur ein sauberer Start.
MQTT_GEDULD_S = 240

log = logging.getLogger("voco-gateway")

# Wird gesetzt, wenn der Dienst enden soll. Unter Windows kommt der Stoppbefehl
# aus der Dienststeuerung, nicht als Strg+C - ohne dieses Signal wuerde der
# Dienst beim Anhalten haengen, bis Windows ihn nach 30 Sekunden abschiesst.
STOPP = threading.Event()


def stoppen() -> None:
    """Von aussen aufrufen, damit der Dienst geordnet endet."""
    STOPP.set()


def load_state() -> set[str]:
    try:
        with open(pfade.zustandsdatei(), encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_state(fired: set[str]):
    # nur die letzten ~500 Eintraege behalten
    try:
        with open(pfade.zustandsdatei(), "w", encoding="utf-8") as f:
            json.dump(sorted(fired)[-500:], f)
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




def protokoll_einrichten(ausfuehrlich: bool = False) -> str:
    """Protokoll auf die Konsole UND in eine Datei.

    Als Systemdienst gibt es kein Fenster: Ohne Datei bliebe im Fehlerfall
    nichts uebrig ausser der Frage, warum nichts laeutet. Die Datei wird bei
    1 MB umgebrochen und drei Staende werden aufgehoben - das reicht fuer
    mehrere Wochen und laeuft nie voll.
    """
    wurzel = logging.getLogger()
    wurzel.setLevel(logging.DEBUG if ausfuehrlich else logging.INFO)
    form = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    konsole = logging.StreamHandler()
    konsole.setFormatter(form)
    wurzel.addHandler(konsole)

    datei = pfade.protokolldatei()
    try:
        in_datei = logging.handlers.RotatingFileHandler(
            datei, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        in_datei.setFormatter(form)
        wurzel.addHandler(in_datei)
    except Exception as e:                      # z. B. kein Schreibrecht
        log.warning("Protokolldatei '%s' nicht nutzbar: %s", datei, e)
        return ""
    return datei


def _zugang() -> tuple[str, str]:
    base = os.environ.get("CT_BASE_URL")
    token = os.environ.get("CT_LOGIN_TOKEN") or os.environ.get("CT_API_TOKEN")
    if not base or not token:
        gefunden = pfade.env_datei()
        raise RuntimeError(
            "CT_BASE_URL und CT_LOGIN_TOKEN fehlen. Gelesene .env: "
            + (gefunden or f"keine gefunden (gesucht neben {pfade.programmordner()})"))
    return base, token


def einmal_laufen(dry: bool, notifier: EmailNotifier, erster_start: bool) -> None:
    """Ein vollstaendiger Dienstlauf: aufbauen, laufen, aufraeumen.

    Kehrt nur zurueck, wenn der Dienst beendet werden soll. Bei jeder Stoerung
    wird eine Ausnahme geworfen - darum kuemmert sich die Dienstschleife.
    """
    base, token = _zugang()
    ct = ChurchTools(base, token)
    cfg = load_from_churchtools(ct)
    # Zugangsdaten aus der Extension haben Vorrang vor der .env.
    notifier.uebernehmen(cfg.email)
    if not cfg.device:
        raise RuntimeError("Kein Geraet konfiguriert (Extension oder .env: "
                           "VOCO_SERIAL/VOCO_DEVICE_PW)")

    log.info("Geraet %s, %d Regel(n)%s", cfg.device.serial, len(cfg.rules),
             "  [SIMULATION - loest NICHT aus]" if dry else "")

    # Ereignisse fuer das Ereignis-Log der Extension. Sie werden dort auch dann
    # sichtbar, wenn zur fraglichen Zeit niemand die Seite offen hatte - das
    # Log im Browser vergisst beim Schliessen alles.
    ereignisse = Ereignisse(ct, EXT_KEY)
    waechter = Zustandswaechter(ereignisse)
    ereignisse.melde("info", ("Automatik-Dienst gestartet." if erster_start
                              else "Automatik-Dienst nach einer Störung neu gestartet.")
                     + (" Simulation: es wird nichts ausgelöst." if dry else ""))

    voco = Voco(serial=cfg.device.serial, device_pw=cfg.device.device_pw,
                broker_url=cfg.device.broker_url)
    # Vor dem Verbinden setzen, damit auch der erste Aufbau protokolliert wird.
    voco.on_zustand = waechter.setze
    try:
        voco.connect()
        voco.request_list()
    except Exception as e:
        log.error("Verbindung zur Steuerung (MQTT) fehlgeschlagen: %s", e)
        ereignisse.melde("aus", f"Verbindungsaufbau zur Anlage fehlgeschlagen: {e}")
        voco.close()
        raise

    fired = load_state()
    plan: list[dict] = []
    last_refresh = 0.0
    # Lebenszeichen: Ohne das sieht in der Extension niemand, ob dieser Dienst
    # ueberhaupt laeuft - ein stiller Ausfall faellt sonst erst auf, wenn ein
    # Gottesdienst ungelaeutet bleibt. 0.0 = gleich beim Start einmal senden.
    beat = Heartbeat(ct, EXT_KEY)
    last_beat = 0.0
    last_outbox = 0.0
    lese_stoerung_seit: float | None = None
    mqtt_weg_seit: float | None = None
    beenden = False

    try:
        while not STOPP.is_set():
            now = time.time()

            # --- Ist die Anlage noch dran? -------------------------------
            # paho verbindet selbst neu. Klappt das ueber Minuten nicht, wird
            # hier abgebrochen: Die Dienstschleife baut dann alles neu auf.
            if voco.c.is_connected():
                mqtt_weg_seit = None
            else:
                if mqtt_weg_seit is None:
                    mqtt_weg_seit = now
                elif now - mqtt_weg_seit > MQTT_GEDULD_S:
                    raise RuntimeError(
                        f"Verbindung zur Anlage seit {int(now - mqtt_weg_seit)} s "
                        "getrennt - der Dienst baut sie neu auf.")

            if now - last_beat > HEARTBEAT_S:
                last_beat = now
                beat.send(rules=len([r for r in cfg.rules if r.active and r.pgs_name]),
                          simulation=dry,
                          device=mask_serial(cfg.device.serial if cfg.device else ""),
                          mail=notifier.enabled and bool(cfg.email and cfg.email.send_feedback))

            # Was die Extension in den Postausgang gestellt hat, verschicken.
            # Nicht bei jedem Tick: Es sind zwei Abfragen, und niemand wartet
            # auf die Sekunde.
            if now - last_outbox > OUTBOX_S:
                last_outbox = now
                try:
                    outbox.verarbeiten(ct, cfg, notifier)
                except Exception as e:
                    # Ein klemmender Postausgang darf das Laeuten nicht anhalten.
                    log.warning("Postausgang konnte nicht verarbeitet werden: %s", e)

            if now - last_refresh > CONFIG_REFRESH_S:
                try:
                    neu = load_from_churchtools(ct)
                    # Eine Konfiguration ohne Geraet ist keine Konfiguration,
                    # sondern eine halb gelesene Antwort (fehlendes Leserecht,
                    # abgelaufene Sitzung). Sie zu uebernehmen hiess frueher:
                    # 0 Regeln, kein Geraet - und beim naechsten Lebenszeichen
                    # ein Absturz. Lieber beim bisherigen Stand bleiben.
                    if neu.device is None:
                        raise RuntimeError("Antwort ohne Geraetedaten - vermutlich "
                                           "fehlende Leseberechtigung oder Aussetzer.")
                    cfg = neu
                    notifier.uebernehmen(cfg.email)
                    plan = build_schedule(ct, cfg)
                    last_refresh = now
                    upcoming = [f"{time.strftime('%H:%M', time.localtime(p['ts']))} → {p['pgs_name']}"
                                for p in plan[:5]]
                    log.info("Plan aktualisiert: %d Ausloesung(en). Naechste: %s",
                             len(plan), ", ".join(upcoming) or "keine")
                    if lese_stoerung_seit is not None:
                        dauer = int((now - lese_stoerung_seit) / 60)
                        ereignisse.melde("an", f"Verbindung zu ChurchTools wieder da "
                                               f"(war {dauer} Minute(n) gestört).")
                        lese_stoerung_seit = None
                except Exception as e:
                    # Der bisherige Plan bleibt bestehen - ein Aussetzer beim
                    # Lesen darf kein Gelaeut ausfallen lassen.
                    if lese_stoerung_seit is None:
                        lese_stoerung_seit = now
                        log.error("Konfig/Termine laden fehlgeschlagen: %s", e)
                        ereignisse.melde("aus", f"ChurchTools nicht erreichbar: {e}")
                    else:
                        log.warning("Konfig/Termine weiterhin nicht ladbar: %s", e)

            for p in plan:
                if p["key"] in fired:
                    continue
                if now >= p["ts"] and now < p["ts"] + FIRE_WINDOW_S:
                    if quiet_now():
                        log.warning("Ruhezeit aktiv – ueberspringe %s (%s)", p["pgs_name"], p["title"])
                        ereignisse.melde("info", f"Ruhezeit aktiv – „{p['pgs_name']}“ "
                                                 f"für „{p['title']}“ übersprungen.")
                        fired.add(p["key"]); save_state(fired)
                        continue
                    raw = voco.resolve(p["pgs_name"]) or p["pgs_name"]
                    if dry:
                        log.info("[SIMULATION] wuerde ausloesen: %s (%s)", decode_name(raw), p["title"])
                        ereignisse.melde("info", f"Simulation: „{decode_name(raw)}“ wäre jetzt "
                                                 f"für „{p['title']}“ ausgelöst worden.")
                    else:
                        try:
                            voco.start(raw)
                            log.info("AUSGELOEST: %s  (Termin: %s)", decode_name(raw), p["title"])
                            ereignisse.melde("an", f"Ausgelöst: „{decode_name(raw)}“ "
                                                   f"für „{p['title']}“.")
                        except Exception as e:
                            log.error("Ausloesen fehlgeschlagen: %s (%s): %s", decode_name(raw), p["title"], e)
                            ereignisse.melde("aus", f"Auslösen fehlgeschlagen: „{decode_name(raw)}“ "
                                                    f"für „{p['title']}“ ({e}).")
                    fired.add(p["key"]); save_state(fired)

            if STOPP.wait(TICK_S):
                beenden = True
                break
    except KeyboardInterrupt:
        beenden = True
    finally:
        # Zuerst melden, dann trennen: Das Trennen loest den Zustandswaechter
        # aus, und "Verbindung verloren" waere beim geplanten Beenden irrefuehrend.
        voco.on_zustand = None
        if beenden:
            log.info("Auf Wunsch beendet.")
            ereignisse.melde("info", "Automatik-Dienst beendet.")
        voco.close()


def dienstschleife(dry: bool, notifier: EmailNotifier) -> None:
    """Haelt den Dienst am Leben, was auch passiert.

    Frueher endete der Prozess bei jeder Stoerung - kein Netz beim Hochfahren,
    ChurchTools kurz nicht erreichbar, abgelaufene Sitzung. Die Aufgabenplanung
    meldete trotzdem Erfolg, und niemand sah, dass seit Stunden nichts mehr
    laeuft. Jetzt wird gewartet und neu versucht; beendet wird nur auf
    ausdruecklichen Wunsch.
    """
    warte = WIEDERANLAUF_MIN_S
    erster_start = True
    while not STOPP.is_set():
        begonnen = time.time()
        try:
            einmal_laufen(dry, notifier, erster_start)
            return
        except KeyboardInterrupt:
            log.info("Beendet.")
            return
        except Exception as e:
            gelaufen = time.time() - begonnen
            if gelaufen > GELUNGEN_AB_S:
                warte = WIEDERANLAUF_MIN_S   # lief lange - war offenbar nur ein Aussetzer
            log.warning("Dienst unterbrochen: %s", e)
            log.info("Neuer Versuch in %d Sekunden.", warte)
            try:
                if STOPP.wait(warte):
                    break
            except KeyboardInterrupt:
                log.info("Beendet.")
                return
            warte = min(warte * 2, WIEDERANLAUF_MAX_S)
            erster_start = False
    log.info("Beendet.")


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Plant, loest aber NICHT aus")
    ap.add_argument("--ausfuehrlich", action="store_true", help="Mehr Protokoll")
    args = ap.parse_args(argv)

    datei = protokoll_einrichten(args.ausfuehrlich)
    env = load_dotenv()

    # Simulation: per Flag ODER dauerhaft per .env (VOCO_SIMULATION=1) -> loest NICHT aus
    sim_env = os.environ.get("VOCO_SIMULATION", "").strip().lower() in ("1", "true", "yes", "on")
    dry = args.dry_run or sim_env

    log.info("Glockensteuerung-Gateway %s startet.", pfade.version())
    log.info("Programmordner: %s", pfade.programmordner())
    log.info("Konfiguration: %s", env or "KEINE .env gefunden")
    if datei:
        log.info("Protokoll: %s", datei)

    # Automatische Fehler-E-Mails (an EMAIL_TO, Standard josua.hess@icloud.com)
    notifier = EmailNotifier()
    log.addHandler(notifier.log_handler())

    dienstschleife(dry, notifier)


if __name__ == "__main__":
    main()
