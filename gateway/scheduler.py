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
import sys
import threading
import time

import aktualisierung
from churchtools import ChurchTools
from config import EXT_KEY, GatewayConfig, Rule, load_dotenv, load_from_churchtools
from ereignisse import Ereignisse, LogWaechter, Zustandswaechter
from heartbeat import Heartbeat, mask_serial
from notify import EmailNotifier
import outbox
import pfade
import sperre
from voco_mqtt import Voco, decode_name

HORIZON_HOURS = 26          # so weit im Voraus planen
CONFIG_REFRESH_S = 300      # Konfig/Termine alle 5 min neu laden
TICK_S = 20                 # so oft pruefen, ob etwas ansteht
OUTBOX_S = 60               # so oft den Postausgang der Extension abarbeiten
FIRE_WINDOW_S = 150         # Toleranz: bis 2,5 min nach Soll noch ausloesen
# So oft ein Lebenszeichen nach ChurchTools geschrieben wird. Zusammen mit
# TICK_S ergibt das einen Schlag alle 40 s. Die Erweiterung meldet einen
# Ausfall nach 2 Minuten - das geht nur auf, wenn oefter geschrieben wird als
# frueher (alle 2 min), sonst waere schon der Normalbetrieb ein Alarm.
HEARTBEAT_S = 30

# Wiederanlauf nach einer Stoerung: erst kurz warten, dann immer laenger, aber
# hoechstens 5 Minuten. Kurz genug, dass ein Aussetzer beim Hochfahren keine
# Rolle spielt; lang genug, dass ein dauerhaft falscher Zugang nicht im
# Sekundentakt ins Protokoll schreibt.
# Der zuletzt aufgebaute Heartbeat und der zuletzt gemeldete Stand. Die
# Dienstschleife greift im Fehlerfall darauf zurueck: Sie hat selbst keine
# Verbindung zu ChurchTools, soll aber melden koennen, dass der Dienst lebt.
LETZTER_BEAT = None
LETZTER_STAND: dict = {}

# So lange gilt Schweigen nach einem geordneten Anhalten als erwartet. Wer den
# Dienst anhaelt, tut das zum Ersetzen der Programmdatei oder fuer einen
# Neustart - beides dauert Minuten. Ohne diese Frist meldete die Erweiterung
# schon nach zwei Minuten einen Ausfall und schickte die dringende E-Mail,
# waehrend jemand danebensass und genau das gerade selbst veranlasst hatte.
# Bleibt der Dienst darueber hinaus weg, ist es ein Ausfall wie jeder andere.
WARTUNGSFENSTER_S = 15 * 60
# So lange gilt eine gesetzte Wartungsmarke. Lang genug fuer das Anhalten eines
# Dienstes, kurz genug, dass eine vergessene Marke nicht spaeter ein echtes
# Anhalten durch Windows verschluckt.
WARTUNG_GILT_S = 120

WIEDERANLAUF_MIN_S = 15
WIEDERANLAUF_MAX_S = 300
# Ab wann ein Lauf als "hat getragen" gilt und die Wartezeit wieder von vorn
# beginnt.
GELUNGEN_AB_S = 600
# Selbstaktualisierung: so oft wird nachgesehen, ob es etwas Neues gibt.
UPDATE_PRUEFUNG_S = 6 * 3600
# So viel Ruhe muss um eine Ausloesung herum sein, damit getauscht wird. Ein
# Neustart dauert Sekunden - aber die falschen Sekunden waeren die vor dem
# Gottesdienst.
UPDATE_RUHE_S = 1800
# So lange darf der Neustart dauern, ohne dass es als Ausfall gilt. Die
# Erweiterung schlaegt in dieser Zeit keinen Alarm: Ein geplanter Neustart ist
# keine Stoerung.
UPDATE_FRIST_MIN = 10

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
    ereignisse.melde("an", ("Automatik-Dienst gestartet und mit ChurchTools verbunden."
                            if erster_start else
                            "Automatik-Dienst nach einer Störung neu gestartet, "
                            "Verbindung zu ChurchTools steht wieder.")
                     + (" Simulation: es wird nichts ausgelöst." if dry else ""))
    # Ab hier landen auch Warnungen und Fehler des Dienstes im Ereignis-Log.
    # Ohne das fand man in ChurchTools einen Dienst, der "nicht erreichbar" war,
    # und keinen Hinweis, woran es lag - der Grund stand allein im Protokoll auf
    # dem Rechner der Gemeinde.
    log_waechter = LogWaechter(ereignisse)
    log.addHandler(log_waechter)

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
    # Auch die Dienstschleife braucht ihn: Wenn hier eine Stoerung hochgeht,
    # soll sie melden koennen, dass der Dienst lebt und neu aufbaut.
    global LETZTER_BEAT, LETZTER_STAND
    LETZTER_BEAT = beat
    last_beat = 0.0
    last_outbox = 0.0
    lese_stoerung_seit: float | None = None
    mqtt_weg_seit: float | None = None
    beenden = False
    # Selbstaktualisierung: Erst pruefen, dann warten, bis nichts brennt.
    auto_update = (getattr(sys, "frozen", False)
                   and os.environ.get("VOCO_AUTO_UPDATE", "1").strip().lower()
                   not in ("0", "false", "nein", "off"))
    letzte_update_pruefung = 0.0
    update_bereit: tuple[str, str] | None = None

    # Steht die beiseitegeschobene Fassung noch daneben, ist dieser Start der
    # erste nach einer Aktualisierung - und damit der Beweis, dass sie laeuft.
    if getattr(sys, "frozen", False) and os.path.exists(sys.executable + ".alt"):
        aktualisierung.aufraeumen()
        ereignisse.melde("an", f"Aktualisierung abgeschlossen - Fassung "
                               f"{pfade.version()} laeuft.")

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
                LETZTER_STAND = {
                    "rules": len([r for r in cfg.rules if r.active and r.pgs_name]),
                    "simulation": dry,
                    "device": mask_serial(cfg.device.serial if cfg.device else ""),
                    "mail": notifier.enabled and bool(cfg.email and cfg.email.send_feedback),
                    "mail_fehler": notifier.enabled and bool(cfg.email and cfg.email.send_errors),
                }
                beat.send(**LETZTER_STAND)

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
                    upcoming = [f"{time.strftime('%H:%M', time.localtime(p['ts']))} "
                                f"→ {decode_name(p['pgs_name'])}"
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

            # --- Selbstaktualisierung --------------------------------
            if auto_update and now - letzte_update_pruefung > UPDATE_PRUEFUNG_S:
                letzte_update_pruefung = now
                update_bereit = aktualisierung.steht_bereit(pfade.version())
                if update_bereit:
                    log.info("Fassung %s liegt bereit.", update_bereit[0])
            if update_bereit and aktualisierung_versuchen(
                    voco, plan, ereignisse, beat, cfg, notifier, dry,
                    update_bereit, now):
                # Der Helfer haelt den Dienst gleich an. Bis dahin nichts mehr
                # anfangen - erst recht nichts ausloesen.
                return

            for p in plan:
                if p["key"] in fired:
                    continue
                if now >= p["ts"] and now < p["ts"] + FIRE_WINDOW_S:
                    if quiet_now():
                        log.warning("Ruhezeit aktiv – ueberspringe %s (%s)",
                                    decode_name(p["pgs_name"]), p["title"])
                        ereignisse.melde("info", f"Ruhezeit aktiv – „{decode_name(p['pgs_name'])}“ "
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
        log.removeHandler(log_waechter)
        if beenden:
            veranlasst = wartung_abholen()
            # Nur wo der Dienst gleich wiederkommt, bleibt es still. Wird er
            # dagegen angehalten und bleibt aus - ob von Hand (Menuepunkt 7)
            # oder von Windows -, gehoert das gemeldet: Bis ihn jemand startet,
            # laeutet nichts.
            if veranlasst in ("neustart", "aktualisierung"):
                # Jemand hat im Menue "anhalten" oder "neu starten" gewaehlt.
                # Er weiss also Bescheid - eine Stoerungsmeldung waere hier
                # nur Laerm. Genau so ging eine dringende E-Mail raus, waehrend
                # der Tausch der Programmdatei lief.
                pause_melden(WARTUNGSFENSTER_S, "Der Dienst wurde angehalten "
                                                "(Wartung oder Neustart).")
            else:
                # Der Dienst bleibt aus. DAS muss auffallen, und zwar sofort.
                # Die Erweiterung kann es nicht: Ihre Meldung liegt im
                # Postausgang, bis der Dienst zurueckkommt - und wenn er nicht
                # zurueckkommt, kommt auch die Meldung nie. Er lebt jetzt noch
                # und kann selbst verschicken; das ist der letzte Augenblick,
                # in dem das geht.
                von_hand = veranlasst == "anhalten"
                log.warning("Der Dienst wird angehalten (%s) und bleibt aus, "
                            "bis ihn jemand startet.",
                            "von Hand" if von_hand else "Befehl von Windows")
                woher = (
                    "Jemand hat ihn von Hand angehalten (Menuepunkt 7) - "
                    "meist, um die Programmdatei zu ersetzen.\n\n"
                    "Nach dem Tausch die neue Datei starten und Punkt 1 "
                    "waehlen, dann laeuft die Automatik wieder."
                    if von_hand else
                    "Den Befehl hat Windows gegeben: ein Update, das "
                    "Herunterfahren des Rechners, der Energiesparmodus oder "
                    "ein anderes Programm.\n\n"
                    "Was in der Ereignisanzeige von Windows steht, sagt, wer "
                    "es war: Windows-Protokolle -> System -> Quelle "
                    "'Service Control Manager'."
                )
                try:
                    notifier.notify(
                        "Die Automatik wurde angehalten",
                        "Der Gateway-Dienst wird gerade angehalten.\n\n"
                        + woher +
                        "\n\nSolange er steht, wird zu den Terminen NICHT "
                        "automatisch gelaeutet.",
                        dringend=True)
                except Exception as e:
                    log.warning("Meldung ueber das Anhalten ging nicht raus: %s", e)
            # Deutlich sagen, WER beendet hat. "Auf Wunsch beendet" las sich wie
            # eine Entscheidung des Programms - dabei kommt der Befehl immer von
            # aussen: aus der Dienststeuerung von Windows (sc stop, services.msc,
            # Menuepunkt 7, Herunterfahren) oder als Strg+C im Fenster. Wer das
            # nicht weiss, sucht den Fehler im Programm statt in Windows.
            log.info("Angehalten - der Befehl kam von der Dienststeuerung "
                     "(Windows) oder als Strg+C. Das Programm beendet sich nie "
                     "von selbst.")
            ereignisse.melde("info", "Automatik-Dienst wurde angehalten "
                                     "(Befehl von Windows).")
        voco.close()


def wartung_abholen() -> str:
    """Wer hat das Anhalten veranlasst? Die Marke gilt einmal und wird entfernt.

    Gesetzt wird sie kurz vor dem Anhalten - vom Menue oder von der
    Selbstaktualisierung - und sie sagt, worum es geht:

      "neustart"        Menuepunkt 6. Der Dienst ist gleich wieder da.
      "aktualisierung"  Selbstaktualisierung. Dasselbe, nur mit neuer Fassung.
      "anhalten"        Menuepunkt 7. Er bleibt aus, bis ihn jemand startet.
      ""                Keine Marke: Windows hat angehalten.

    Sie verfaellt nach kurzer Zeit: Eine liegengebliebene duerfte ein echtes
    Anhalten durch Windows nicht Stunden spaeter noch stumm schalten.
    """
    pfad = pfade.wartungsmarke()
    try:
        alter = time.time() - os.path.getmtime(pfad)
        with open(pfad, encoding="utf-8") as f:
            grund = f.read(40).strip()
    except Exception:
        return ""
    try:
        os.remove(pfad)
    except Exception:
        pass
    if alter >= WARTUNG_GILT_S:
        return ""
    return grund or "anhalten"


def pause_melden(warte_s: float, grund: str) -> None:
    """Sagt der Erweiterung, dass der Dienst lebt und gerade neu aufbaut.

    Ohne das sah sie nur, dass kein Lebenszeichen mehr kommt - und meldete
    einen Ausfall samt E-Mail, obwohl der Dienst nach Sekunden wieder da war.
    Der Wiederanlauf dauert 15 Sekunden bis 5 Minuten; die Erweiterung meldet
    schon nach zwei Minuten. Das traf sich denkbar schlecht.

    Schlaegt das Schreiben fehl, ist das kein Drama: Dann ist ChurchTools
    gerade auch nicht erreichbar - und ein Ausfall ist dann die richtige
    Meldung.
    """
    if LETZTER_BEAT is None:
        return
    bis = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=warte_s + HEARTBEAT_S)
    try:
        LETZTER_BEAT.send(**{**{"rules": 0, "simulation": True, "device": ""},
                             **LETZTER_STAND},
                          pause_bis=bis, grund=grund)
    except Exception:
        pass


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
            pause_melden(warte, str(e))
            try:
                if STOPP.wait(warte):
                    break
            except KeyboardInterrupt:
                log.info("Beendet.")
                return
            warte = min(warte * 2, WIEDERANLAUF_MAX_S)
            erster_start = False
    log.info("Beendet.")


def nichts_brennt(voco, plan: list[dict], now: float) -> tuple[bool, str]:
    """Darf der Dienst gerade neu starten?

    Zwei Gruende sprechen dagegen, und beide waeren im Nachhinein nicht mehr
    gutzumachen: Es laeutet gerade, oder es soll gleich laeuten.
    """
    try:
        if voco.stop_raw:
            return False, "es laeutet gerade"
    except Exception:
        pass
    for p in plan:
        abstand = p["ts"] - now
        if -UPDATE_RUHE_S < abstand < UPDATE_RUHE_S:
            wann = time.strftime("%H:%M", time.localtime(p["ts"]))
            return False, f"um {wann} steht eine Ausloesung an"
    return True, ""


def aktualisierung_versuchen(voco, plan, ereignisse, beat, cfg, notifier, dry,
                             bereit: tuple[str, str], now: float) -> bool:
    """Spielt eine bereitliegende Fassung ein. Gibt zurueck, ob neu gestartet wird.

    Die Meldungen gehen bewusst als Information ins Ereignis-Log, nicht als
    Stoerung: Ein geplanter Neustart ist keiner. Gemeldet wird erst, wenn der
    Dienst sich danach nicht wieder zurueckmeldet - und das sieht die
    Erweiterung, nicht er selbst.
    """
    version, url = bereit
    frei, grund = nichts_brennt(voco, plan, now)
    if not frei:
        log.info("Aktualisierung auf %s wartet: %s.", version, grund)
        return False

    log.info("Aktualisierung auf %s wird geladen.", version)
    datei = aktualisierung.herunterladen(url)
    if not datei:
        ereignisse.melde("info", f"Fassung {version} konnte nicht geladen werden. "
                                 "Es bleibt vorerst beim bisherigen Stand.")
        return False

    # Kurz davor noch einmal nachsehen: Der Download hat gedauert, und in der
    # Zwischenzeit kann eine Ausloesung naeher gerueckt sein.
    frei, grund = nichts_brennt(voco, plan, time.time())
    if not frei:
        log.info("Aktualisierung auf %s verschoben: %s.", version, grund)
        return False

    if not aktualisierung.einspielen(datei):
        ereignisse.melde("info", f"Fassung {version} liess sich nicht einsetzen. "
                                 "Es bleibt beim bisherigen Stand.")
        return False

    # Das Lebenszeichen traegt die Frist: Bis dahin ist Schweigen erwartet und
    # loest in der Erweiterung keine Stoerungsmeldung aus.
    beat.send(rules=len([r for r in cfg.rules if r.active and r.pgs_name]),
              simulation=dry,
              device=mask_serial(cfg.device.serial if cfg.device else ""),
              mail=notifier.enabled and bool(cfg.email and cfg.email.send_feedback),
              mail_fehler=notifier.enabled and bool(cfg.email and cfg.email.send_errors),
              update_bis=dt.datetime.now(dt.timezone.utc)
              + dt.timedelta(minutes=UPDATE_FRIST_MIN))
    ereignisse.melde("info", f"Aktualisierung auf Fassung {version} eingespielt. "
                             "Der Dienst startet jetzt neu und meldet sich gleich "
                             "wieder.")
    log.info("Aktualisierung auf %s eingespielt - Neustart wird angestossen.", version)
    if not aktualisierung.neustart_anstossen():
        ereignisse.melde("info", "Der Neustart liess sich nicht anstossen. Die neue "
                                 "Fassung wird beim naechsten Start benutzt.")
        return False
    return True


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

    # Erst sichern, dass kein zweiter Gateway laeuft. Zwei gleichzeitig loesen
    # dasselbe Gelaeut zweimal aus - und das faellt nicht im Protokoll auf,
    # sondern im Dorf.
    if not sperre.belegen():
        log.error("Es laeuft bereits ein Gateway auf diesem Rechner. Dieser Start "
                  "wird beendet, damit nicht doppelt gelaeutet wird.")
        log.error("Laeuft noch eine alte Einrichtung? Eine Aufgabe in der "
                  "Aufgabenplanung oder ein von Hand gestartetes 'python "
                  "scheduler.py' sind die haeufigsten Gruende.")
        return

    log.info("Glockensteuerung-Gateway %s startet.", pfade.version())
    # Altlast aus frueheren Fassungen selbst richten: Ein verzoegert
    # eingetragener Dienst laeuft erst zwei Minuten nach dem Hochfahren an.
    # Der Dienst darf das aendern - er laeuft als SYSTEM -, und so muss
    # niemand dafuer noch einmal durch das Einrichten.
    try:
        import windienst
        if windienst.VERFUEGBAR and windienst.verzoegerung_abstellen():
            log.info("Der Dienst war auf verzoegerten Start eingestellt und "
                     "startet ab dem naechsten Hochfahren sofort.")
    except Exception as e:
        log.debug("Starttyp nicht pruefbar: %s", e)
    log.info("Programmordner: %s", pfade.programmordner())
    log.info("Konfiguration: %s", env or "KEINE .env gefunden")
    if datei:
        log.info("Protokoll: %s", datei)

    # Automatische Fehler-E-Mails (an EMAIL_TO, Standard josua.hess@icloud.com)
    notifier = EmailNotifier()
    log.addHandler(notifier.log_handler())

    try:
        dienstschleife(dry, notifier)
    finally:
        sperre.freigeben()


if __name__ == "__main__":
    main()
