"""
Wo der Dienst seine Dateien sucht - unabhaengig vom Arbeitsverzeichnis.

Der Grund ist eine Falle, die auf dem Rechner der Gemeinde zuschlug: Ein
Aufgabenplanungs-Eintrag ohne "Starten in" startet den Prozess im
Windows-Systemverzeichnis. Dort liegt keine .env, der Dienst brach sofort mit
"CT_BASE_URL und CT_LOGIN_TOKEN in .env noetig" ab - im Taskmanager war er
trotzdem kurz zu sehen, was den Eindruck erweckte, er liefe.

Deshalb wird hier nicht mehr geraten, sondern gerechnet: Massgeblich ist der
Ordner, in dem das Programm selbst liegt (bei der EXE also neben der EXE), nicht
der, aus dem es aufgerufen wurde.
"""
from __future__ import annotations
import os
import sys

# Dateien, die neben dem Programm erwartet werden. Die .env bleibt, wo sie ist -
# niemand muss sie anfassen oder umziehen.
ENV_DATEI = ".env"
ZUSTAND_DATEI = "state.json"
PROTOKOLL_DATEI = "gateway.log"


def programmordner() -> str:
    """Ordner des Programms: neben der EXE, sonst neben den Python-Modulen."""
    if getattr(sys, "frozen", False):        # von PyInstaller gebaute EXE
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _suchorte() -> list[str]:
    """Wo nach mitgebrachten Dateien gesucht wird - in dieser Reihenfolge.

    Der Unterordner 'gateway' ist dabei, weil das Archiv genau so entpackt wird:
    Wer die EXE eine Ebene darueber ablegt, soll trotzdem seine .env finden.
    """
    orte = [programmordner(), os.path.join(programmordner(), "gateway")]
    try:
        hier = os.getcwd()
        orte += [hier, os.path.join(hier, "gateway")]
    except Exception:
        pass
    gesehen, ergebnis = set(), []
    for o in orte:
        o = os.path.abspath(o)
        if o not in gesehen:
            gesehen.add(o)
            ergebnis.append(o)
    return ergebnis


def finde(name: str) -> str | None:
    """Erste vorhandene Datei dieses Namens, oder None."""
    for ort in _suchorte():
        pfad = os.path.join(ort, name)
        if os.path.exists(pfad):
            return pfad
    return None


def env_datei() -> str | None:
    """Die .env - dort, wo sie schon liegt. VOCO_ENV_FILE geht vor."""
    vorgabe = os.environ.get("VOCO_ENV_FILE", "").strip()
    if vorgabe:
        return vorgabe if os.path.exists(vorgabe) else None
    return finde(ENV_DATEI)


def arbeitsordner() -> str:
    """Ordner fuer selbst geschriebene Dateien (Zustand, Protokoll).

    Normalerweise der Programmordner - dort sucht man zuerst, und dort liegt bei
    dieser Installation auch alles andere. Laesst sich dort nicht schreiben
    (etwa unter C:\\Program Files), wird nach ProgramData ausgewichen, statt den
    Dienst daran scheitern zu lassen.
    """
    eigen = os.environ.get("VOCO_DATA_DIR", "").strip()
    kandidaten = [eigen] if eigen else []
    kandidaten.append(programmordner())
    basis = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA")
    if basis:
        kandidaten.append(os.path.join(basis, "Glockensteuerung"))
    kandidaten.append(os.path.expanduser("~"))

    for ordner in kandidaten:
        try:
            os.makedirs(ordner, exist_ok=True)
            probe = os.path.join(ordner, ".schreibprobe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return ordner
        except Exception:
            continue
    return programmordner()


def zustandsdatei() -> str:
    """Merkliste bereits ausgeloester Termine (verhindert Doppellaeuten)."""
    vorgabe = os.environ.get("VOCO_STATE_FILE", "").strip()
    if vorgabe:
        return vorgabe
    # Eine bereits vorhandene Datei gewinnt - sonst faenge der Dienst nach einem
    # Umzug des Arbeitsordners von vorn an und koennte einen gerade gelaeuteten
    # Termin ein zweites Mal ausloesen.
    da = finde(ZUSTAND_DATEI)
    return da or os.path.join(arbeitsordner(), ZUSTAND_DATEI)


def protokolldatei() -> str:
    """Laufendes Protokoll. Ohne das sieht niemand, warum der Dienst schweigt:
    Als Systemdienst gibt es kein Fenster, in dem etwas stehen koennte."""
    return os.path.join(arbeitsordner(), PROTOKOLL_DATEI)


def version() -> str:
    """Welcher Stand laeuft hier?

    In der fertigen Programmdatei steckt die Nummer als Modul 'version' - beim
    Bauen hineingeschrieben. Im Quelltextbetrieb gibt es das Modul nicht; dann
    wird eine Datei VERSION gesucht, wie sie frueher im Archiv lag.
    """
    try:
        from version import VERSION       # nur in der gebauten Programmdatei
        if VERSION:
            return str(VERSION)
    except Exception:
        pass
    pfad = finde("VERSION")
    if pfad:
        try:
            with open(pfad, encoding="utf-8") as f:
                return f.read().strip() or "(unbekannt)"
        except Exception:
            pass
    return "(unbekannt)"
