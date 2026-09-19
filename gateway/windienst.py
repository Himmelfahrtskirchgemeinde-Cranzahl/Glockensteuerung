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

    # Verspaeteter Start: Beim Hochfahren ist das Netz oft noch nicht da. Der
    # Dienst faengt sich zwar selbst, aber so beginnt sein Protokoll nicht mit
    # einer Fehlermeldung.
    _sc("config", NAME, "start=", "delayed-auto")
    # Faellt der Dienst aus, startet Windows ihn nach einer Minute neu - immer
    # wieder, nicht nur die ersten drei Male ("reset= 0" setzt den Zaehler nie
    # zurueck, also gilt die dritte Regel dauerhaft).
    _sc("failure", NAME, "reset=", "0",
        "actions=", "restart/60000/restart/60000/restart/60000")
    return 0


def starten() -> int:
    import win32serviceutil
    try:
        win32serviceutil.StartService(NAME)
        print("Dienst gestartet.")
        return 0
    except Exception as e:
        print(f"Der Dienst konnte nicht gestartet werden: {e}")
        return 1


def anhalten() -> int:
    import win32serviceutil
    try:
        win32serviceutil.StopService(NAME)
        print("Dienst angehalten.")
        return 0
    except Exception as e:
        print(f"Der Dienst laeuft nicht oder liess sich nicht anhalten: {e}")
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
