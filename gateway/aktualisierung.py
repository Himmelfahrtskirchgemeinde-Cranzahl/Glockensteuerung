"""
Der Dienst haelt sich selbst auf dem neuesten Stand.

Warum ueberhaupt: Eine Korrektur am Gateway nuetzt nichts, solange niemand an
den Rechner der Gemeinde geht. Bis dahin laeuft dort die alte Fassung - mit dem
Fehler, der gerade behoben wurde.

Drei Regeln, die den Unterschied zwischen hilfreich und gefaehrlich ausmachen:

1. **Nur, wenn es den Gateway betrifft.** Eine neue Fassung der Erweiterung
   aendert an diesem Programm nichts. Entschieden wird das am Changelog des
   Release: Steht dort ein Abschnitt "Gateway", ist etwas fuer uns dabei.

2. **Nur, wenn nichts brennt.** Waehrend gelaeutet wird oder kurz vor einer
   Ausloesung wird nicht getauscht. Ein Neustart dauert Sekunden - aber die
   falschen Sekunden waeren die vor dem Gottesdienst.

3. **Der Weg zurueck bleibt offen.** Die bisherige Programmdatei wird nicht
   geloescht, sondern umbenannt. Startet die neue nicht, liegt die alte
   daneben.

Was hier NICHT passiert: Es wird nichts ausgefuehrt, was heruntergeladen wurde,
ohne es vorher anzusehen. Die Datei muss von GitHub kommen, eine plausible
Groesse haben und mit der Kennung eines Windows-Programms beginnen.
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import urllib.request

import pfade

log = logging.getLogger("voco-gateway")

REPO = "Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
PROGRAMMDATEI = "Glockensteuerung-Gateway.exe"

# Kleiner als das kann die Programmdatei nicht sein (sie enthaelt Python).
MINDESTGROESSE = 3 * 1024 * 1024
# So lange darf ein Download dauern.
ZEITGRENZE_S = 120


def _version_teile(text: str) -> tuple[int, ...]:
    """'26.10.1' -> (26, 10, 1). Unbekanntes wird zu (0,)."""
    teile = []
    for stueck in str(text or "").strip().lstrip("v").split("."):
        ziffern = "".join(c for c in stueck if c.isdigit())
        if not ziffern:
            break
        teile.append(int(ziffern))
    return tuple(teile) or (0,)


def ist_neuer(neu: str, alt: str) -> bool:
    """Ist 'neu' eine hoehere Version als 'alt'?

    Vergleicht Stelle fuer Stelle als Zahlen: '26.10.0' ist hoeher als '26.9.9',
    obwohl es alphabetisch kleiner waere. Die vierte Stelle eines Hotfix
    (26.9.0.1) zaehlt genauso mit.
    """
    a, b = _version_teile(neu), _version_teile(alt)
    laenge = max(len(a), len(b))
    a += (0,) * (laenge - len(a))
    b += (0,) * (laenge - len(b))
    return a > b


def betrifft_gateway(changelog: str) -> bool:
    """Steht im Changelog etwas ueber den Gateway?

    Seit 26.10 trennt die Release-Beschreibung die beiden Teile. Aeltere
    Beschreibungen kennen diese Trennung nicht - bei ihnen wird angenommen,
    dass es den Gateway betrifft. Lieber einmal zu viel aktualisieren als eine
    Korrektur verpassen, die niemand bemerkt.
    """
    text = changelog or ""
    hat_teile = ("## Erweiterung" in text) or ("## Gateway" in text)
    if not hat_teile:
        return True
    return "## Gateway" in text


def neueste_fassung(zeitgrenze: float = 15.0) -> tuple[str, str, str] | None:
    """Fragt GitHub nach dem neuesten Release.

    Rueckgabe: (Version, Changelog, URL der Programmdatei) - oder None, wenn
    sich nichts abrufen laesst. Ein Fehler hier ist kein Drama: Dann bleibt
    eben alles, wie es ist, und beim naechsten Mal wird erneut gefragt.
    """
    try:
        anfrage = urllib.request.Request(
            RELEASES_API,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "Glockensteuerung-Gateway"})
        with urllib.request.urlopen(anfrage, timeout=zeitgrenze) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except Exception as e:
        log.info("Aktualisierungspruefung nicht moeglich: %s", e)
        return None

    version = str(daten.get("tag_name") or "").lstrip("v")
    if not version:
        return None
    changelog = str(daten.get("body") or "")
    url = ""
    for datei in daten.get("assets") or []:
        if str(datei.get("name")) == PROGRAMMDATEI:
            url = str(datei.get("browser_download_url") or "")
            break
    if not url:
        return None
    return version, changelog, url


def steht_bereit(eigene_version: str) -> tuple[str, str] | None:
    """Gibt es etwas Neues, das uns betrifft? Rueckgabe: (Version, URL)."""
    fassung = neueste_fassung()
    if not fassung:
        return None
    version, changelog, url = fassung
    if not ist_neuer(version, eigene_version):
        return None
    if not betrifft_gateway(changelog):
        log.info("Version %s ist da, aendert aber nichts am Gateway.", version)
        return None
    return version, url


def _pruefen_und_ablegen(rohdaten: bytes, ziel: str) -> bool:
    """Sieht sich das Heruntergeladene an, bevor es abgelegt wird."""
    if len(rohdaten) < MINDESTGROESSE:
        log.warning("Heruntergeladene Datei ist nur %d Bytes gross - das kann "
                    "die Programmdatei nicht sein.", len(rohdaten))
        return False
    if rohdaten[:2] != b"MZ":
        log.warning("Heruntergeladene Datei ist kein Windows-Programm.")
        return False
    with open(ziel, "wb") as f:
        f.write(rohdaten)
    return True


def herunterladen(url: str) -> str | None:
    """Laedt die neue Programmdatei neben die alte. Gibt ihren Pfad zurueck."""
    ziel = os.path.join(pfade.programmordner(), PROGRAMMDATEI + ".neu")
    try:
        anfrage = urllib.request.Request(
            url, headers={"User-Agent": "Glockensteuerung-Gateway"})
        with urllib.request.urlopen(anfrage, timeout=ZEITGRENZE_S) as antwort:
            rohdaten = antwort.read()
    except Exception as e:
        log.warning("Neue Fassung konnte nicht geladen werden: %s", e)
        return None
    try:
        if not _pruefen_und_ablegen(rohdaten, ziel):
            return None
    except Exception as e:
        log.warning("Neue Fassung konnte nicht abgelegt werden: %s", e)
        return None
    return ziel


def einspielen(neue_datei: str) -> bool:
    """Tauscht die Programmdatei aus. Die bisherige bleibt daneben liegen.

    Windows laesst sich eine laufende Programmdatei nicht ueberschreiben - wohl
    aber UMBENENNEN. Genau das wird hier ausgenutzt: Die laufende wandert zur
    Seite, die neue nimmt ihren Platz ein. Beim naechsten Start laeuft die neue.
    """
    eigen = os.path.abspath(os.sys.executable)
    alt = eigen + ".alt"
    try:
        if os.path.exists(alt):
            os.remove(alt)
    except Exception:
        pass          # liegt noch vom letzten Mal da - stoert nicht weiter
    try:
        os.replace(eigen, alt)
    except Exception as e:
        log.warning("Bisherige Programmdatei liess sich nicht beiseiteschieben: %s", e)
        return False
    try:
        os.replace(neue_datei, eigen)
    except Exception as e:
        log.error("Neue Programmdatei liess sich nicht einsetzen (%s) - die "
                  "bisherige wird zurueckgeholt.", e)
        try:
            os.replace(alt, eigen)
        except Exception:
            log.error("Auch das Zurueckholen scheiterte. Die bisherige Fassung "
                      "liegt als '%s' daneben.", alt)
        return False
    return True


def neustart_anstossen() -> bool:
    """Laesst den Dienst neu starten - durch einen Helfer, der uns ueberlebt.

    Ein Dienst kann sich nicht selbst anhalten und wieder starten: Nach dem
    Anhalten gibt es niemanden mehr, der den Start ausloest. Der Helfer ist
    deshalb ein eigener Prozess, der kurz wartet und dann beides tut.
    """
    if os.name != "nt":
        return False
    import subprocess
    befehl = ("ping -n 6 127.0.0.1 >nul & "
              "sc stop Glockensteuerung >nul & "
              "ping -n 6 127.0.0.1 >nul & "
              "sc start Glockensteuerung >nul")
    try:
        subprocess.Popen(["cmd", "/c", befehl],
                         creationflags=0x00000008 | 0x08000000)  # DETACHED | NO_WINDOW
        return True
    except Exception as e:
        log.warning("Neustart konnte nicht angestossen werden: %s", e)
        return False


def aufraeumen() -> None:
    """Raeumt die beiseitegeschobene Fassung weg - nach gegluecktem Start.

    Erst jetzt, im laufenden Betrieb der neuen Fassung, ist bewiesen, dass sie
    startet. Vorher waere das Loeschen leichtsinnig.
    """
    reste = [os.path.abspath(os.sys.executable) + ".alt",
             os.path.join(pfade.programmordner(), PROGRAMMDATEI + ".neu")]
    for pfad in reste:
        try:
            if os.path.exists(pfad):
                os.remove(pfad)
        except Exception:
            pass
