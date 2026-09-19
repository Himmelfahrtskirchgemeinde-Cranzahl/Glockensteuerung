#!/usr/bin/env python3
"""
Bedienung des Gateway-Dienstes - einmal einrichten, danach laeuft er von selbst.

Diese Datei wird zu EINER Programmdatei gebaut (Glockensteuerung-Gateway.exe).
Sie braucht kein Python, keine virtuelle Umgebung, keine Pfadangaben und keine
Aufgabenplanung:

    Doppelklick            -> kleines Menue (einrichten, Status, Protokoll)
    --installieren         -> fragt die Zugangsdaten ab und legt den Dienst an
    --einstellungen        -> Zugangsdaten, Simulation, Ruhezeit, E-Mail, Geraet
    --entfernen            -> nimmt ihn wieder heraus
    --status               -> laeuft er? was steht im Protokoll?
    --neustart             -> Dienst anhalten und wieder starten
    --testlauf             -> laeuft sichtbar im Fenster, loest NICHTS aus
    --diagnose             -> prueft die Zertifikatskette zum Broker
    --dienst               -> Dauerbetrieb im Vordergrund (ohne Dienststeuerung)
    --windows-dienst       -> so ruft WINDOWS den Dienst auf, nicht von Hand

Die Konfiguration bleibt, wo sie ist: Die .env wird neben der Programmdatei
gesucht (siehe pfade.py). Niemand muss sie anfassen oder umziehen.

Warum ein Dienst und keine Aufgabe: siehe windienst.py. Falls pywin32 fehlt -
etwa bei einem Betrieb aus dem Quelltext heraus -, wird ersatzweise ein
Eintrag in der Aufgabenplanung angelegt; die fertige Programmdatei bringt
pywin32 mit und braucht das nicht.
"""
from __future__ import annotations
import argparse
import ctypes
import os
import subprocess
import sys
import tempfile

import pfade
import windienst

AUFGABE = "Glockensteuerung Gateway"
# Erst starten, wenn das Netz eine Chance hatte (nur fuer den Ersatzweg ueber
# die Aufgabenplanung; der Dienst selbst startet "verzoegert automatisch").
START_VERZOEGERUNG = "PT30S"


def ist_windows() -> bool:
    return os.name == "nt"


def ist_admin() -> bool:
    if not ist_windows():
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def programmdatei() -> str:
    """Die EXE selbst - oder, wenn aus dem Quelltext gestartet, diese Datei."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def als_admin_neu_starten(argumente: list[str]) -> int:
    """Dasselbe Programm noch einmal starten, diesmal mit Adminrechten (UAC).

    Das erspart die Erklaerung, warum ein Administratorkonto allein nicht
    genuegt: Windows gibt einem angemeldeten Administrator standardmaessig ein
    Fenster OHNE erhoehte Rechte, und 'Zugriff verweigert' ist dann die einzige
    Rueckmeldung.
    """
    if not ist_windows():
        print("Bitte als root ausfuehren.")
        return 1
    exe = os.path.abspath(sys.executable)
    if getattr(sys, "frozen", False):
        parameter = " ".join(argumente + ["--warten"])
    else:
        parameter = " ".join([f'"{os.path.abspath(__file__)}"'] + argumente + ["--warten"])
    print("Dafuer werden Administratorrechte gebraucht - Windows fragt gleich nach.")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, parameter, None, 1)
    if rc <= 32:
        print(f"Die Anfrage wurde abgelehnt oder scheiterte (Code {rc}).")
        print("Dann bitte eine Eingabeaufforderung mit Rechtsklick > 'Als "
              "Administrator ausfuehren' oeffnen und es dort erneut versuchen.")
        return 1
    print("Es geht im neuen Fenster weiter.")
    return 0


# --- Alte Eintraege in der Aufgabenplanung --------------------------------

def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True)


def _text(roh: bytes) -> str:
    """Ausgabe von schtasks lesbar machen - die Kodierung wechselt je nach Schalter."""
    for kodierung in ("utf-16-le", "utf-8", "cp1252", "cp850"):
        try:
            t = roh.decode(kodierung)
            if "\x00" not in t:
                return t.lstrip("﻿")
        except Exception:
            continue
    return roh.decode("latin-1", "replace")


def alte_aufgaben() -> list[str]:
    """Findet Aufgaben, die den Gateway starten.

    Wichtig, weil zwei laufende Gateways dasselbe Gelaeut zweimal ausloesen
    wuerden - und weil sonst niemand versteht, warum es nach dem Umstieg auf
    den Dienst doppelt bimmelt.
    """
    if not ist_windows():
        return []
    p = _schtasks("/Query", "/XML", "ONE")
    if p.returncode != 0:
        return []
    text = _text(p.stdout)
    gefunden = []
    for block in text.split("<Task "):
        if not any(kennzeichen in block for kennzeichen in
                   ("scheduler.py", "Glockensteuerung-Gateway.exe", "dienst.py")):
            continue
        anfang, ende = block.find("<URI>"), block.find("</URI>")
        if anfang >= 0 and ende > anfang:
            name = block[anfang + 5:ende].strip()
            if name:
                gefunden.append(name)
    return gefunden


def aufgaben_aufraeumen() -> None:
    for name in alte_aufgaben():
        print(f"Alte Aufgabe in der Aufgabenplanung gefunden: {name}")
        _schtasks("/End", "/TN", name)
        p = _schtasks("/Change", "/TN", name, "/DISABLE")
        print("  -> deaktiviert (der Dienst uebernimmt ab jetzt)." if p.returncode == 0 else
              "  -> liess sich nicht deaktivieren. Bitte von Hand deaktivieren, "
              "sonst laeutet es doppelt.")


# --- Ersatzweg: Aufgabenplanung -------------------------------------------

def aufgabe_xml() -> str:
    if getattr(sys, "frozen", False):
        befehl, argumente = programmdatei(), "--dienst"
    else:
        # Dieselbe python.exe verwenden, mit der dieses Skript laeuft - sonst
        # fehlt der Aufgabe spaeter paho oder requests.
        befehl = os.path.abspath(sys.executable)
        argumente = f'"{programmdatei()}" --dienst'
    ordner = os.path.dirname(programmdatei())
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Laeutet Glocken automatisch zu den Terminen aus ChurchTools.</Description>
    <URI>\\{AUFGABE}</URI>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>{START_VERZOEGERUNG}</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{befehl}</Command>
      <Arguments>{argumente}</Arguments>
      <WorkingDirectory>{ordner}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def aufgabe_einrichten() -> int:
    """Ersatzweg, wenn pywin32 fehlt: Eintrag in der Aufgabenplanung."""
    pfad = os.path.join(tempfile.gettempdir(), "glockensteuerung-aufgabe.xml")
    # schtasks liest die XML-Datei als UTF-16 - anders geht es nicht.
    with open(pfad, "w", encoding="utf-16") as f:
        f.write(aufgabe_xml())
    try:
        p = _schtasks("/Create", "/TN", AUFGABE, "/XML", pfad, "/F")
        if p.returncode != 0:
            print("Die Aufgabe konnte nicht angelegt werden:")
            print(_text(p.stdout) + _text(p.stderr))
            return 1
        print(f"Aufgabe '{AUFGABE}' eingerichtet (Ersatzweg ohne pywin32).")
    finally:
        try:
            os.remove(pfad)
        except Exception:
            pass
    p = _schtasks("/Run", "/TN", AUFGABE)
    print("Der Gateway laeuft jetzt." if p.returncode == 0 else
          "Er konnte nicht sofort gestartet werden - beim naechsten Hochfahren "
          "geschieht das von selbst.")
    return 0


# --- Einrichten, entfernen, nachsehen -------------------------------------

def _konfiguration_sicherstellen() -> bool:
    """Sorgt dafuer, dass Zugangsdaten da sind - notfalls durch Nachfragen.

    Absichtlich VOR der Rechteerhoehung: Die Fragen beantwortet ein Mensch im
    Fenster, das er gerade offen hat. Im erhoehten Fenster liegt die Datei dann
    schon vor und es wird nicht erneut gefragt.
    """
    env = pfade.env_datei()
    if env:
        print(f"Konfiguration gefunden: {env}")
        return True
    print("Neben dem Programm liegt noch keine Konfiguration.")
    import einrichtung
    return einrichtung.assistent()


def einstellungen() -> int:
    """Alles, was frueher von Hand in die .env geschrieben wurde."""
    import einrichtung
    vorher = _konfigurationsstand()
    einrichtung.einstellungen()
    # Der Dienst liest die Datei beim Start. Aendert sich etwas, waehrend er
    # laeuft, merkt er davon nichts - deshalb hier gleich neu starten.
    if ist_windows() and windienst.zustand() == "laeuft" and _konfigurationsstand() != vorher:
        print()
        print("Der Dienst laeuft - damit er die neuen Angaben benutzt, wird er")
        print("jetzt neu gestartet.")
        neustart()
    return 0


def _konfigurationsstand() -> str:
    """Fingerabdruck der .env - um zu erkennen, ob sich etwas geaendert hat."""
    pfad = pfade.env_datei()
    if not pfad:
        return ""
    try:
        with open(pfad, "rb") as f:
            import hashlib
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def installieren() -> int:
    if not ist_windows():
        print("Diese Einrichtung gibt es nur fuer Windows. Unter Linux gehoert der "
              "Gateway in eine systemd-Unit (siehe README).")
        return 1

    if not _konfiguration_sicherstellen():
        print()
        print("Ohne Zugangsdaten wird der Dienst nicht eingerichtet.")
        return 1

    if not ist_admin():
        return als_admin_neu_starten(["--installieren"])
    # Zuerst aufraeumen: Ein alter Eintrag wuerde denselben Gateway ein zweites
    # Mal starten, und dann laeutet es doppelt.
    aufgaben_aufraeumen()

    if not windienst.VERFUEGBAR:
        print("Hinweis: pywin32 ist nicht installiert - es wird der Ersatzweg "
              "ueber die Aufgabenplanung benutzt.")
        print("         Mit 'pip install pywin32' gibt es stattdessen einen "
              "richtigen Windows-Dienst.")
        return aufgabe_einrichten()

    if windienst.einrichten() != 0:
        return 1
    if windienst.starten() != 0:
        print("Beim naechsten Hochfahren startet er trotzdem von selbst.")
    print()
    print("Fertig. Der Dienst steht jetzt in services.msc unter "
          f"'{windienst.ANZEIGENAME}':")
    print("  - er startet beim Hochfahren, ohne dass sich jemand anmeldet,")
    print("  - Windows startet ihn nach einem Absturz von selbst neu,")
    print("  - und er haelt die Verbindung selbst wieder her, wenn sie abreisst.")
    print()
    print("Zur Kontrolle: dieses Programm mit --status aufrufen, oder in "
          "ChurchTools ins Ereignis-Log sehen.")
    return 0


def entfernen() -> int:
    if not ist_windows():
        return 1
    if not ist_admin():
        return als_admin_neu_starten(["--entfernen"])
    aufgaben_aufraeumen()
    if windienst.VERFUEGBAR:
        return windienst.entfernen()
    _schtasks("/End", "/TN", AUFGABE)
    p = _schtasks("/Delete", "/TN", AUFGABE, "/F")
    print("Aufgabe entfernt." if p.returncode == 0 else
          "Es war nichts zu entfernen.")
    return 0


def neustart() -> int:
    if not ist_admin():
        return als_admin_neu_starten(["--neustart"])
    if not windienst.VERFUEGBAR:
        _schtasks("/End", "/TN", AUFGABE)
        _schtasks("/Run", "/TN", AUFGABE)
        print("Aufgabe neu gestartet.")
        return 0
    windienst.anhalten()
    return windienst.starten()


def status() -> int:
    print(f"Glockensteuerung-Gateway {pfade.version()}")
    print(f"Programm:      {programmdatei()}")
    print(f"Konfiguration: {pfade.env_datei() or 'KEINE .env gefunden'}")
    print(f"Protokoll:     {pfade.protokolldatei()}")
    if ist_windows():
        print(f"Dienst:        {windienst.zustand()}")
        uebrig = alte_aufgaben()
        if uebrig:
            print("ACHTUNG:       Es gibt noch Aufgaben, die den Gateway ebenfalls "
                  "starten: " + ", ".join(uebrig))
            print("               Solange die aktiv sind, kann es doppelt laeuten "
                  "(--installieren raeumt sie weg).")
    print()
    protokoll(15)
    return 0


def protokoll(zeilen: int = 40) -> int:
    datei = pfade.protokolldatei()
    if not os.path.exists(datei):
        print(f"Noch kein Protokoll vorhanden ({datei}).")
        return 0
    print(f"Die letzten {zeilen} Zeilen aus {datei}:")
    try:
        with open(datei, encoding="utf-8", errors="replace") as f:
            alle = f.readlines()
        for z in alle[-zeilen:]:
            print("  " + z.rstrip())
    except Exception as e:
        print(f"Protokoll nicht lesbar: {e}")
    return 0


def menue() -> int:
    """Was bei einem Doppelklick passiert."""
    print(f"Glockensteuerung-Gateway {pfade.version()}")
    print("=" * 56)
    if ist_windows():
        print(f"Dienst: {windienst.zustand()}")
    if not pfade.env_datei():
        print("Noch nicht eingerichtet - dafuer ist Punkt 1 da.")
    print()
    print(" 1  Einrichten: Zugangsdaten abfragen und Dienst anlegen")
    print(" 2  Einstellungen (Zugang, Simulation, Ruhezeit, E-Mail, Geraet)")
    print(" 3  Status und Protokoll ansehen")
    print(" 4  Testlauf im Fenster (loest NICHTS aus)")
    print(" 5  Verbindung pruefen (Zertifikate)")
    print(" 6  Dienst neu starten")
    print(" 7  Dienst wieder entfernen")
    print(" 0  Schliessen")
    print()
    try:
        wahl = input("Auswahl: ").strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    if wahl == "1":
        rc = installieren()
    elif wahl == "2":
        rc = einstellungen()
    elif wahl == "3":
        rc = status()
    elif wahl == "4":
        import scheduler
        scheduler.main(["--dry-run"])
        rc = 0
    elif wahl == "5":
        import diagnose
        diagnose.main()
        rc = 0
    elif wahl == "6":
        rc = neustart()
    elif wahl == "7":
        rc = entfernen()
    else:
        return 0
    if not ist_admin():         # im erhoehten Fenster wartet bereits --warten
        try:
            input("\nMit der Eingabetaste schliessen ...")
        except Exception:
            pass
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("--windows-dienst", action="store_true",
                    help="Nur fuer Windows: Start durch die Dienststeuerung")
    ap.add_argument("--dienst", action="store_true", help="Dauerbetrieb im Vordergrund")
    ap.add_argument("--installieren", action="store_true")
    ap.add_argument("--einstellungen", "--einrichten", action="store_true",
                    dest="einstellungen",
                    help="Zugang, Simulation, Ruhezeit, E-Mail und Geraet pflegen")
    ap.add_argument("--entfernen", action="store_true")
    ap.add_argument("--neustart", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--protokoll", action="store_true")
    ap.add_argument("--testlauf", action="store_true", help="Laeuft im Fenster, loest NICHTS aus")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--warten", action="store_true",
                    help="Am Ende auf eine Taste warten (fuer das UAC-Fenster)")
    args = ap.parse_args(argv)

    rc = 0
    if args.windows_dienst:
        windienst.im_dienstbetrieb_starten()
    elif args.dienst:
        import scheduler
        scheduler.main([])
    elif args.installieren:
        rc = installieren()
    elif args.einstellungen:
        rc = einstellungen()
    elif args.entfernen:
        rc = entfernen()
    elif args.neustart:
        rc = neustart()
    elif args.status:
        rc = status()
    elif args.protokoll:
        rc = protokoll()
    elif args.testlauf:
        import scheduler
        scheduler.main(["--dry-run"])
    elif args.diagnose:
        import diagnose
        diagnose.main()
    else:
        return menue()

    if args.warten:
        try:
            input("\nMit der Eingabetaste schliessen ...")
        except Exception:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
