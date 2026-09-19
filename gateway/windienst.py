#!/usr/bin/env python3
"""
Der Gateway als echter Windows-Dienst.

Die Aufgabenplanung war der falsche Ort dafuer. Sie ist dafuer gemacht, etwas
zu einem Zeitpunkt zu STARTEN - nicht, etwas dauerhaft am Leben zu halten. Wer
dort einen Dauerlaeufer eintraegt, kaempft mit einer Reihe von Dingen, die
nichts mit dem Laeuten zu tun haben: dem Konto, unter dem die Aufgabe laeuft,
dem Arbeitsverzeichnis, dem Ausfuehrungszeitlimit, der Frage, ob die Aufgabe
"laeuft" oder nur eingetragen ist.

Ein Dienst kennt diese Fragen nicht. Er steht in services.msc, startet
automatisch beim Hochfahren des Rechners - ohne dass sich jemand anmeldet -,
und wenn er abstuerzt, startet Windows ihn selbst neu. Das ist genau das
Verhalten, das hier gebraucht wird.

Gebraucht wird dafuer pywin32 (in requirements.txt, nur unter Windows).
Bedient wird der Dienst ueber dienst.py bzw. die fertige Programmdatei.
"""
from __future__ import annotations
import os
import sys

NAME = "Glockensteuerung"
ANZEIGENAME = "Glockensteuerung Gateway"
BESCHREIBUNG = ("Laeutet die Glocken automatisch zu den Terminen aus ChurchTools "
                "und meldet sich dort regelmaessig zurueck.")

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    VERFUEGBAR = True
except ImportError:                     # Linux, oder pywin32 fehlt
    VERFUEGBAR = False


if VERFUEGBAR:

    class GlockenDienst(win32serviceutil.ServiceFramework):
        _svc_name_ = NAME
        _svc_display_name_ = ANZEIGENAME
        _svc_description_ = BESCHREIBUNG

        def __init__(self, args):
            super().__init__(args)
            self.warten = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            """Windows moechte den Dienst anhalten."""
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            import scheduler
            scheduler.stoppen()
            win32event.SetEvent(self.warten)

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (self._svc_name_, ""))
            import scheduler
            try:
                scheduler.main([])
            except Exception:
                # Im Ereignisprotokoll von Windows landet sonst nur "Dienst
                # unerwartet beendet" - ohne den geringsten Hinweis, warum.
                import logging
                logging.getLogger("voco-gateway").exception(
                    "Der Dienst ist mit einem unerwarteten Fehler beendet worden.")
                raise


def _dienstklasse():
    """Die Klasse so vorbereiten, dass sie auch als EXE registrierbar ist.

    Bei einer mit PyInstaller gebauten Programmdatei gibt es keine python.exe,
    die Windows aufrufen koennte. Deshalb wird die Programmdatei selbst als
    auszufuehrendes Programm eingetragen - mit dem Schalter, der sie in den
    Dienstbetrieb schickt.
    """
    if getattr(sys, "frozen", False):
        GlockenDienst._exe_name_ = os.path.abspath(sys.executable)
        GlockenDienst._exe_args_ = "--windows-dienst"
    return GlockenDienst


def im_dienstbetrieb_starten() -> None:
    """Wird aufgerufen, wenn WINDOWS den Dienst startet (nicht ein Mensch)."""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(_dienstklasse())
    servicemanager.StartServiceCtrlDispatcher()


def _sc(*args: str) -> int:
    import subprocess
    return subprocess.run(["sc", *args], capture_output=True).returncode


def einrichten() -> int:
    """Dienst anlegen (oder aktualisieren) und starten."""
    import win32serviceutil
    klasse = _dienstklasse()
    try:
        win32serviceutil.InstallService(
            None if getattr(sys, "frozen", False) else f"{__name__}.GlockenDienst",
            NAME, ANZEIGENAME, description=BESCHREIBUNG,
            startType=win32service.SERVICE_AUTO_START,
            exeName=getattr(klasse, "_exe_name_", None),
            exeArgs=getattr(klasse, "_exe_args_", None),
        )
        print(f"Dienst '{ANZEIGENAME}' angelegt.")
    except Exception as e:
        if "existiert bereits" in str(e) or "already exists" in str(e) or "1073" in str(e):
            win32serviceutil.ChangeServiceConfig(
                None if getattr(sys, "frozen", False) else f"{__name__}.GlockenDienst",
                NAME, displayName=ANZEIGENAME, description=BESCHREIBUNG,
                startType=win32service.SERVICE_AUTO_START,
                exeName=getattr(klasse, "_exe_name_", None),
                exeArgs=getattr(klasse, "_exe_args_", None),
            )
            print(f"Dienst '{ANZEIGENAME}' aktualisiert.")
        else:
            print(f"Der Dienst konnte nicht angelegt werden: {e}")
            return 1

    # Sofort mit dem Hochfahren starten - NICHT "delayed-auto". Windows laesst
    # verzoegerte Dienste erst 120 Sekunden nach den uebrigen anlaufen; zwei
    # Minuten, in denen nicht gelaeutet wuerde und in denen der Dienst wie
    # ausgefallen aussieht.
    #
    # Der frueher dafuer angefuehrte Grund - beim Hochfahren ist das Netz oft
    # noch nicht da - traegt nicht mehr: Die Dienstschleife faengt genau das ab
    # und versucht es nach 15 Sekunden erneut. Damit es gar nicht erst dazu
    # kommt, haengt der Dienst jetzt an den Netzwerkdiensten: Windows startet
    # ihn erst, wenn TCP/IP und die Namensaufloesung stehen.
    _sc("config", NAME, "start=", "auto", "depend=", "Tcpip/Dnscache")
    # Faellt der Dienst aus, startet Windows ihn nach einer Minute neu - immer
    # wieder, nicht nur die ersten drei Male ("reset= 0" setzt den Zaehler nie
    # zurueck, also gilt die dritte Regel dauerhaft).
    _sc("failure", NAME, "reset=", "0",
        "actions=", "restart/60000/restart/60000/restart/60000")
    return 0


def warte_auf(ziel: str, sekunden: float = 30.0) -> bool:
    """Wartet, bis der Dienst den Zustand erreicht. True, wenn er ihn erreicht.

    Noetig, weil StopService und StartService zurueckkehren, sobald Windows den
    Befehl ANGENOMMEN hat - nicht, wenn er ausgefuehrt ist. Wer direkt danach
    starten will, trifft den Dienst mitten im Anhalten an, und der Start
    scheitert. Genau daran lag es, dass ein Neustart zweimal noetig war.
    """
    import time
    ende = time.time() + sekunden
    while time.time() < ende:
        if zustand() == ziel:
            return True
        time.sleep(0.5)
    return zustand() == ziel


def starten() -> int:
    import win32serviceutil
    try:
        win32serviceutil.StartService(NAME)
    except Exception as e:
        print(f"Der Dienst konnte nicht gestartet werden: {e}")
        return 1
    # Erst melden, wenn er wirklich laeuft - sonst steht "Dienst gestartet" da,
    # waehrend der Start noch aussteht oder gleich wieder abbricht.
    if warte_auf("laeuft"):
        print("Dienst gestartet.")
        return 0
    print(f"Der Dienst wurde gestartet, laeuft aber (noch) nicht: {zustand()}.")
    print("Was dabei schiefging, steht in gateway.log daneben.")
    return 1


# Windows-Fehler 1062: "Der Dienst wurde nicht gestartet." Wer anhalten will,
# was ohnehin steht, hat sein Ziel bereits erreicht - das ist kein Fehler.
NICHT_GESTARTET = 1062


def _fehlernummer(e: Exception) -> int:
    """Windows-Fehlernummer aus einer pywin32-Ausnahme, sonst 0."""
    nr = getattr(e, "winerror", None)
    if isinstance(nr, int):
        return nr
    args = getattr(e, "args", ())
    return args[0] if args and isinstance(args[0], int) else 0


def anhalten() -> int:
    """Haelt den Dienst an. Ein bereits angehaltener Dienst ist kein Fehler."""
    import win32serviceutil
    try:
        win32serviceutil.StopService(NAME)
        # Abwarten, bis er wirklich steht. Windows nimmt den Befehl sofort an,
        # braucht danach aber noch einen Moment; wer gleich weitermacht (etwa
        # die Programmdatei ersetzt oder neu startet), laeuft sonst ins Leere.
        if not warte_auf("angehalten"):
            print(f"Der Dienst haelt noch an (Zustand: {zustand()}).")
            return 1
        print("Dienst angehalten.")
        return 0
    except Exception as e:
        if _fehlernummer(e) == NICHT_GESTARTET:
            # (Der Dienst stand schon - dann ist auch nichts abzuwarten.)
            # Frueher stand hier "Der Dienst laeuft nicht ODER liess sich nicht
            # anhalten" samt Windows-Fehlertext. Das las sich wie eine Stoerung,
            # obwohl alles in Ordnung war - beim Neustart erschien es jedes Mal,
            # wenn der Dienst vorher schon stand.
            print("Der Dienst lief nicht - es gibt nichts anzuhalten.")
            return 0
        print(f"Der Dienst liess sich nicht anhalten: {e}")
        return 1


def entfernen() -> int:
    import win32serviceutil
    try:
        win32serviceutil.StopService(NAME)
    except Exception:
        pass
    try:
        win32serviceutil.RemoveService(NAME)
        print("Dienst entfernt.")
        return 0
    except Exception as e:
        print(f"Der Dienst liess sich nicht entfernen: {e}")
        return 1


def programmpfad() -> str:
    """Welche Programmdatei der eingetragene Dienst startet.

    Wichtig beim Wechsel auf eine neue Fassung: Liegt die neue Datei woanders
    (oder heisst sie anders), startet Windows weiter die alte - und niemand
    versteht, warum die Neuerungen ausbleiben.
    """
    if not VERFUEGBAR:
        return ""
    try:
        import win32service
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            dienst = win32service.OpenService(scm, NAME, win32service.SERVICE_QUERY_CONFIG)
            try:
                return str(win32service.QueryServiceConfig(dienst)[3] or "")
            finally:
                win32service.CloseServiceHandle(dienst)
        finally:
            win32service.CloseServiceHandle(scm)
    except Exception:
        return ""


def zeigt_auf(datei: str) -> bool:
    """Startet der eingetragene Dienst genau diese Programmdatei?"""
    eingetragen = programmpfad()
    if not eingetragen:
        return False
    # Im Eintrag stehen Anfuehrungszeichen und Argumente mit drin.
    teil = eingetragen.strip()
    if teil.startswith('"'):
        teil = teil[1:].split('"', 1)[0]
    else:
        teil = teil.split(" ", 1)[0]
    return os.path.normcase(os.path.abspath(teil)) == os.path.normcase(os.path.abspath(datei))


def verzoegerung_abstellen() -> bool:
    """Stellt einen verzoegerten Start auf sofort um. True, wenn geaendert.

    Frueher wurde der Dienst als "delayed-auto" eingetragen; Windows laesst
    solche Dienste erst 120 Sekunden nach den uebrigen anlaufen. Wer schon
    eingerichtet hat, saesse sonst weiter auf den zwei Minuten - und muesste
    dafuer von Hand noch einmal durch Punkt 1.

    Der Dienst laeuft als SYSTEM und darf das selbst richten. Umgestellt wird
    NUR von "verzoegert" auf "sofort", also innerhalb des automatischen Starts.
    Wer bewusst "nur von Hand" oder "deaktiviert" gewaehlt hat, behaelt das:
    Das waere eine Entscheidung, keine Altlast.
    """
    if not VERFUEGBAR or not starttyp().startswith("automatisch (verz"):
        return False
    if _sc("config", NAME, "start=", "auto", "depend=", "Tcpip/Dnscache") != 0:
        return False
    return True


def starttyp() -> str:
    """Startet der Dienst beim Hochfahren von selbst? Klartext.

    Das ist die wichtigste Frage ueberhaupt: Ein Dienst, der nur laeuft, weil
    ihn jemand gestartet hat, ist nach dem naechsten Neustart des Rechners weg
    - und niemand merkt es, bis ein Gottesdienst ungelaeutet bleibt. Im Status
    stand bisher nur, ob er GERADE laeuft.
    """
    if not VERFUEGBAR:
        return "unbekannt (pywin32 fehlt)"
    import win32service
    try:
        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            h = win32service.OpenService(h_scm, NAME, win32service.SERVICE_QUERY_CONFIG)
            try:
                cfg = win32service.QueryServiceConfig(h)
                typ = cfg[1]
                verzoegert = False
                try:
                    verzoegert = bool(win32service.QueryServiceConfig2(
                        h, win32service.SERVICE_CONFIG_DELAYED_AUTO_START_INFO))
                except Exception:
                    pass
            finally:
                win32service.CloseServiceHandle(h)
        finally:
            win32service.CloseServiceHandle(h_scm)
    except Exception:
        return "nicht eingerichtet"
    if typ == win32service.SERVICE_AUTO_START:
        return "automatisch (verzoegert)" if verzoegert else "automatisch"
    if typ == win32service.SERVICE_DEMAND_START:
        return "nur von Hand"
    if typ == win32service.SERVICE_DISABLED:
        return "deaktiviert"
    return f"Typ {typ}"


def startet_von_selbst() -> bool:
    """Faengt der Dienst beim Hochfahren von selbst an zu laufen?"""
    return starttyp().startswith("automatisch")


def zustand() -> str:
    """Kurzer Klartext: laeuft er, steht er, gibt es ihn ueberhaupt?"""
    if not VERFUEGBAR:
        return "unbekannt (pywin32 fehlt)"
    import win32serviceutil
    try:
        code = win32serviceutil.QueryServiceStatus(NAME)[1]
    except Exception:
        return "nicht eingerichtet"
    return {
        win32service.SERVICE_STOPPED: "angehalten",
        win32service.SERVICE_START_PENDING: "startet gerade",
        win32service.SERVICE_STOP_PENDING: "haelt gerade an",
        win32service.SERVICE_RUNNING: "laeuft",
        win32service.SERVICE_PAUSED: "angehalten (pausiert)",
    }.get(code, f"Zustand {code}")
