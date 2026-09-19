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
    --anhalten             -> Dienst anhalten (um die Programmdatei zu ersetzen)
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


def _eigene_module_schuetzen() -> None:
    """Verhindert, dass alte Dateien neben der Programmdatei geladen werden.

    Im Ordner koennen noch die Python-Dateien einer frueheren Installation
    liegen (aus dem Archiv, das es bis 26.8 gab). Wuerde eine davon statt des
    eingebauten Moduls geladen, liefe eine halb alte, halb neue Fassung - der
    schlimmste denkbare Zustand, weil nichts davon sichtbar waere.

    In der gebauten Programmdatei steckt ohnehin alles; der eigene Ordner hat
    im Suchpfad deshalb nichts zu suchen.
    """
    if not getattr(sys, "frozen", False):
        return
    ordner = os.path.dirname(os.path.abspath(sys.executable))
    sys.path[:] = [p for p in sys.path
                   if os.path.abspath(p or ".") != ordner]


def ist_windows() -> bool:
    return os.name == "nt"


def ist_admin() -> bool:
    if not ist_windows():
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# Wird beim Einrichten gesetzt, falls die Programmdatei an einen festen Ort
# gebracht wurde. Eingetragen werden soll dann die Kopie, nicht das Original.
_ZIELDATEI = ""


def programmdatei() -> str:
    """Die EXE selbst - oder, wenn aus dem Quelltext gestartet, diese Datei."""
    if _ZIELDATEI:
        return _ZIELDATEI
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


# Rueckgabewert von als_admin_neu_starten(): Die Arbeit laeuft ab jetzt in
# einem zweiten, erhoehten Fenster. Dieses hier hat nichts mehr zu tun und darf
# NICHT ins Menue zurueckkehren - sonst staenden zwei Menues offen und man
# bediente das falsche.
IM_ANDEREN_FENSTER = 99


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
    return IM_ANDEREN_FENSTER


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

# Wohin der Dienst gehoert, wenn niemand etwas anderes sagt. Bewusst kurz und
# auf der Systemplatte: Der Dienst laeuft als SYSTEM und muss den Ordner auch
# dann erreichen, wenn niemand angemeldet ist.
STANDARDORT = r"C:\Glockensteuerung"

# Orte, an denen eine Programmdatei nicht dauerhaft liegen sollte. Aus dem
# Download-Ordner wird aufgeraeumt, der Desktop wird umsortiert, und was im
# Temp-Ordner liegt, loescht Windows selbst - der Dienst zeigte danach ins
# Leere und schwiege.
UNGEEIGNET = ("\\downloads", "\\download", "\\desktop", "\\temp",
              "\\tmp", "\\onedrive", "\\papierkorb", "\\recycle")


def _ort_taugt(ordner: str) -> bool:
    # Bewusst nicht ueber os.path.normcase: Das tut ausserhalb von Windows
    # NICHTS - die Pruefung liefe auf jedem anderen System ins Leere und waere
    # dort auch nicht zu pruefen. Hier wird deshalb selbst vereinheitlicht.
    kleines = os.path.abspath(ordner).replace("/", "\\").lower()
    return not any(teil in kleines for teil in UNGEEIGNET)


def _an_festen_ort_bringen() -> str:
    """Sorgt dafuer, dass die Programmdatei dauerhaft liegt, wo sie hingehoert.

    Der Pfad ist beim Einrichten die wichtigste Angabe: Er wird im Dienst
    eingetragen. Liegt die Datei im Download-Ordner, zeigt der Eintrag dorthin -
    und beim naechsten Aufraeumen schweigen die Glocken, ohne dass jemand einen
    Zusammenhang sieht.

    Gibt den Pfad der Programmdatei zurueck, die eingetragen werden soll.
    """
    eigene = programmdatei()
    hier = os.path.dirname(eigene)

    if not getattr(sys, "frozen", False):
        return eigene          # aus dem Quelltext heraus wird nichts verschoben

    print()
    print(f"Programmdatei: {eigene}")
    if _ort_taugt(hier):
        print("Dieser Ordner wird im Dienst eingetragen.")
        if not _ja("Soll sie woanders hin?", standard=False):
            return eigene
        ziel_vorgabe = hier
    else:
        print("Dieser Ordner taugt nicht auf Dauer: Aus Download-, Desktop- und")
        print("Temp-Ordnern wird aufgeraeumt - der Dienst zeigte danach ins Leere.")
        ziel_vorgabe = STANDARDORT

    ziel = _frage("In welchen Ordner soll sie?", ziel_vorgabe)
    if not ziel or os.path.normcase(os.path.abspath(ziel)) == os.path.normcase(hier):
        return eigene

    try:
        os.makedirs(ziel, exist_ok=True)
    except Exception as e:
        print(f"Der Ordner liess sich nicht anlegen ({e}). Es bleibt beim bisherigen.")
        return eigene

    neu = os.path.join(ziel, os.path.basename(eigene))
    import shutil
    try:
        if os.path.normcase(neu) != os.path.normcase(eigene):
            shutil.copy2(eigene, neu)
    except Exception as e:
        print(f"Die Datei liess sich nicht kopieren ({e}). Es bleibt beim bisherigen Ordner.")
        return eigene

    # Was danebenliegt, gehoert mit: ohne .env keine Zugangsdaten, ohne
    # state.json koennte ein gerade gelaeuteter Termin erneut ausloesen.
    for name in (pfade.ENV_DATEI, pfade.ZUSTAND_DATEI):
        quelle = os.path.join(hier, name)
        ziel_datei = os.path.join(ziel, name)
        if os.path.exists(quelle) and not os.path.exists(ziel_datei):
            try:
                shutil.copy2(quelle, ziel_datei)
                print(f"  {name} mitgenommen")
            except Exception as e:
                print(f"  {name} konnte nicht mitgenommen werden: {e}")

    print(f"Die Programmdatei liegt jetzt hier: {neu}")
    print("Die heruntergeladene Datei kann danach geloescht werden.")
    # Ab hier gelten die Dateien am neuen Ort - auch fuer die Einrichtung.
    pfade.programmordner = lambda: ziel      # type: ignore[assignment]
    return neu


def _frage(text: str, vorgabe: str = "") -> str:
    import einrichtung
    return einrichtung._frage(text, vorgabe)


def _ja(text: str, standard: bool = True) -> bool:
    import einrichtung
    return einrichtung._ja(text, standard)


def _energiesparen() -> tuple[bool, str]:
    """Geht der Rechner im Netzbetrieb von selbst schlafen?

    Der Dienst laeuft unabhaengig von Anmeldung, Benutzerwechsel und Sperre -
    aber nicht, wenn der Rechner schlaeft. Das ist die letzte Luecke im
    Dauerbetrieb, und sie faellt erst auf, wenn ein Gottesdienst stumm bleibt.

    Rueckgabe: (schlaeft_ein, Klartext). Laesst sich der Wert nicht lesen, gilt
    das als "unbekannt" - dann wird trotzdem angeboten, ihn abzuschalten.
    """
    if not ist_windows():
        return False, ""
    p = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"],
                       capture_output=True)
    if p.returncode != 0:
        return True, "unbekannt"
    text = _text(p.stdout)
    # Sprachunabhaengig: Die erste Hex-Zahl nach "AC"/"Wechselstrom" ist der
    # Wert fuer den Netzbetrieb. Die Beschriftung wechselt mit der Sprache, die
    # Reihenfolge nicht - Netzbetrieb steht immer vor Akkubetrieb.
    import re
    werte = re.findall(r"0x([0-9a-fA-F]{8})", text)
    if len(werte) < 2:
        return True, "unbekannt"
    sekunden = int(werte[-2], 16)      # vorletzter Wert = Netzbetrieb
    if sekunden == 0:
        return False, "aus"
    return True, f"nach {sekunden // 60} Minuten"


def _energiesparen_abschalten() -> None:
    """Fragt nach und stellt den Rechner auf Dauerbetrieb um."""
    schlaeft, wie = _energiesparen()
    if not schlaeft:
        return
    print()
    print("Energiesparen: Der Rechner geht im Netzbetrieb schlafen"
          + (f" ({wie})." if wie != "unbekannt" else " - oder koennte es."))
    print("Solange er schlaeft, laeuft der Dienst nicht und es wird nicht gelaeutet.")
    if not _ja("Standby im Netzbetrieb abschalten?", standard=True):
        print("Unveraendert. Bitte daran denken, dass ein schlafender Rechner "
              "nicht laeutet.")
        return
    for schalter in ("standby-timeout-ac", "hibernate-timeout-ac"):
        subprocess.run(["powercfg", "/change", schalter, "0"], capture_output=True)
    schlaeft, _ = _energiesparen()
    print("Erledigt - der Rechner bleibt im Netzbetrieb wach." if not schlaeft else
          "Das hat nicht geklappt. Bitte in den Energieoptionen von Hand auf "
          "\"Niemals\" stellen.")


def _verknuepfung_anlegen(ziel: str) -> None:
    """Legt eine Verknuepfung im Startmenue an.

    Nach der Einrichtung verschwindet die Programmdatei aus dem Blick - sie
    liegt in einem Ordner, den niemand im Alltag oeffnet. Gebraucht wird sie
    aber wieder: fuer die Einstellungen, den Status, das Protokoll. Ueber das
    Startmenue ist sie mit einem Tippen da.
    """
    if not ist_windows():
        return
    basis = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    ordner = os.path.join(basis, "Microsoft", "Windows", "Start Menu", "Programs")
    verknuepfung = os.path.join(ordner, "Glockensteuerung.lnk")
    befehl = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut('{verknuepfung}'); "
        f"$s.TargetPath = '{ziel}'; "
        f"$s.WorkingDirectory = '{os.path.dirname(ziel)}'; "
        "$s.Description = 'Glockensteuerung: Einstellungen, Status, Protokoll'; "
        "$s.Save()"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", befehl], capture_output=True)
    if p.returncode == 0:
        print("Im Startmenue liegt jetzt \"Glockensteuerung\" - darueber sind die")
        print("Einstellungen jederzeit erreichbar.")


def _bestand_melden() -> None:
    """Sagt, was schon da ist - und was davon unangetastet bleibt.

    Beim Wechsel auf eine neue Fassung ist das die wichtigste Frage: Muss ich
    alles neu eintragen? Nein - und das soll man lesen, statt es hoffen zu
    muessen.
    """
    gefunden = []
    env = pfade.env_datei()
    if env:
        gefunden.append(f"Zugangsdaten:   {env}")
    zustand = pfade.zustandsdatei()
    if os.path.exists(zustand):
        gefunden.append(f"Gemerkte Ausloesungen: {zustand}")
    protokoll = pfade.protokolldatei()
    if os.path.exists(protokoll):
        gefunden.append(f"Protokoll:      {protokoll}")

    schon_da = ist_windows() and windienst.VERFUEGBAR and windienst.zustand() != "nicht eingerichtet"
    if not gefunden and not schon_da:
        return

    print()
    print("Vorhandene Einrichtung gefunden:")
    for zeile in gefunden:
        print("  " + zeile)
    if schon_da:
        alt = windienst.programmpfad()
        if windienst.zeigt_auf(programmdatei()):
            print("  Dienst:         bereits eingetragen, wird aktualisiert")
        else:
            print(f"  Dienst:         eingetragen auf eine ANDERE Datei")
            if alt:
                print(f"                  ({alt})")
            print("                  Er wird gleich auf diese hier umgestellt.")
    print("Nichts davon wird ueberschrieben - alles wird weiterbenutzt.")


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

    # Erst nachsehen, was schon da ist. Eine neue Fassung soll an einer
    # laufenden Anlage nichts umwerfen: Zugangsdaten, gemerkte Ausloesungen und
    # das Protokoll bleiben, wo sie sind, und werden weiterbenutzt.
    _bestand_melden()

    # Der Pfad ist die wichtigste Angabe beim Einrichten - er landet im Dienst.
    global _ZIELDATEI
    _ZIELDATEI = _an_festen_ort_bringen()

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

    # Zeigt der Eintrag noch auf eine andere Datei, muss der alte Dienst erst
    # stehen: Sonst laeuft die alte Fassung weiter, und unter Windows liesse
    # sich ihre Programmdatei nicht einmal ersetzen.
    if windienst.zustand() == "laeuft" and not windienst.zeigt_auf(programmdatei()):
        print()
        print("Die bisherige Fassung wird angehalten ...")
        windienst.anhalten()

    if windienst.einrichten() != 0:
        return 1
    if windienst.starten() != 0:
        print("Beim naechsten Hochfahren startet er trotzdem von selbst.")
    _verknuepfung_anlegen(programmdatei())
    _energiesparen_abschalten()

    print()
    print("Fertig. Der Dienst steht jetzt in services.msc unter "
          f"'{windienst.ANZEIGENAME}':")
    print("  - er startet beim Hochfahren, ohne dass sich jemand anmeldet,")
    print("  - er laeuft weiter, wenn der Rechner gesperrt wird, sich jemand")
    print("    abmeldet oder ein anderer Benutzer sich anmeldet,")
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
    basis = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    try:
        os.remove(os.path.join(basis, "Microsoft", "Windows", "Start Menu",
                               "Programs", "Glockensteuerung.lnk"))
    except Exception:
        pass          # war keine da - dann ist auch nichts aufzuraeumen
    if windienst.VERFUEGBAR:
        return windienst.entfernen()
    _schtasks("/End", "/TN", AUFGABE)
    p = _schtasks("/Delete", "/TN", AUFGABE, "/F")
    print("Aufgabe entfernt." if p.returncode == 0 else
          "Es war nichts zu entfernen.")
    return 0


def wartung_ankuendigen(grund: str) -> None:
    """Sagt dem laufenden Dienst, wer ihn gleich anhaelt und warum.

    Davon haengt ab, ob es eine Meldung gibt:

      "neustart"  Menuepunkt 6 - er ist gleich wieder da, also still.
      "anhalten"  Menuepunkt 7 - er bleibt aus, das gehoert gemeldet.

    Ohne Marke gilt das Anhalten als Befehl von Windows und wird ebenfalls
    gemeldet. Genau so soll es sein: Haelt Windows den Dienst an (Update,
    Herunterfahren, Virenscanner), muss das auffallen.

    Die Marke ist eine kleine Datei neben dem Programm; der Dienst holt sie
    beim Beenden ab und entfernt sie dabei.
    """
    try:
        with open(pfade.wartungsmarke(), "w", encoding="utf-8") as f:
            f.write(grund)
    except Exception as e:
        # Kein Abbruch: Dann kommt eben eine Meldung zu viel.
        print(f"Hinweis: Die Wartungsmarke liess sich nicht setzen ({e}).")
        print("Es kann deshalb eine Stoerungsmeldung geben, obwohl alles in Ordnung ist.")


def neustart() -> int:
    if not ist_admin():
        return als_admin_neu_starten(["--neustart"])
    wartung_ankuendigen("neustart")
    if not windienst.VERFUEGBAR:
        _schtasks("/End", "/TN", AUFGABE)
        _schtasks("/Run", "/TN", AUFGABE)
        print("Aufgabe neu gestartet.")
        return 0
    # Erst sagen, was ueberhaupt ansteht: Laeuft der Dienst gar nicht, wird er
    # nur gestartet - und niemand raetselt, warum das Anhalten "nicht ging".
    if windienst.zustand() == "laeuft":
        print("Dienst wird angehalten ...")
        if windienst.anhalten() != 0:
            print()
            print("Der Neustart wurde abgebrochen, weil sich der Dienst nicht")
            print("anhalten liess. Er laeuft also weiter.")
            return 1
    else:
        print("Der Dienst laeuft gerade nicht - er wird jetzt gestartet.")
    print("Dienst wird gestartet ...")
    return windienst.starten()


def anhalten() -> int:
    """Haelt den Dienst an - noetig, um die Programmdatei zu ersetzen.

    Windows sperrt die Datei eines laufenden Dienstes. Wer eine neue Fassung
    darueberkopieren will, bekommt sonst nur "Zugriff verweigert" und keinen
    Hinweis, woran es liegt.
    """
    if not ist_admin():
        return als_admin_neu_starten(["--anhalten"])
    # Bewusst "anhalten" und nicht schweigen: Der Dienst bleibt jetzt aus, bis
    # ihn jemand startet. Daran soll eine Meldung erinnern - auch wenn man es
    # selbst veranlasst hat und der Tausch der Programmdatei dazwischenkommt.
    wartung_ankuendigen("anhalten")
    if not windienst.VERFUEGBAR:
        _schtasks("/End", "/TN", AUFGABE)
        print("Angehalten.")
        return 0
    rc = windienst.anhalten()
    print()
    print("Jetzt laesst sich die Programmdatei ersetzen. Danach die neue Datei")
    print("starten und Punkt 1 waehlen - die Zugangsdaten bleiben erhalten.")
    return rc


def status() -> int:
    print(f"Glockensteuerung-Gateway {pfade.version()}")
    print(f"Programm:      {programmdatei()}")
    print(f"Konfiguration: {pfade.env_datei() or 'KEINE .env gefunden'}")
    print(f"Protokoll:     {pfade.protokolldatei()}")
    if ist_windows():
        print(f"Dienst:        {windienst.zustand()}")
        # Die wichtigere Frage als "laeuft er gerade": Faengt er nach einem
        # Neustart des Rechners von selbst wieder an? Stand bisher nirgends.
        eingerichtet = windienst.VERFUEGBAR and windienst.zustand() != "nicht eingerichtet"
        if eingerichtet:
            print(f"Startet:       {windienst.starttyp()}")
            if windienst.starttyp().startswith("automatisch (verz"):
                # Alter Eintrag aus frueheren Fassungen: Windows laesst solche
                # Dienste erst 120 Sekunden nach den uebrigen anlaufen. Der
                # Dienst stellt das beim naechsten Start selbst um - hier steht
                # nur, warum es beim letzten Hochfahren noch gedauert hat.
                print("               (verzoegert - noch der alte Eintrag. Der")
                print("               Dienst stellt das beim naechsten Start")
                print("               selbst auf sofort um.)")
            if not windienst.startet_von_selbst():
                print("ACHTUNG:       Nach einem Neustart des Rechners bleibt der")
                print("               Dienst aus - es wird dann nicht gelaeutet.")
                print("               Punkt 1 (Installieren) stellt das richtig;")
                print("               Zugangsdaten bleiben dabei erhalten.")
        if eingerichtet and not windienst.zeigt_auf(programmdatei()):
            print(f"ACHTUNG:       Der Dienst startet eine ANDERE Datei:")
            print(f"               {windienst.programmpfad()}")
            print("               Diese hier wird also nicht benutzt. Mit "
                  "--installieren umstellen.")
        uebrig = alte_aufgaben()
        if uebrig:
            print("ACHTUNG:       Es gibt noch Aufgaben, die den Gateway ebenfalls "
                  "starten: " + ", ".join(uebrig))
            print("               Solange die aktiv sind, kann es doppelt laeuten "
                  "(--installieren raeumt sie weg).")
        schlaeft, wie = _energiesparen()
        if schlaeft:
            print("ACHTUNG:       Der Rechner geht im Netzbetrieb schlafen"
                  + (f" ({wie})." if wie != "unbekannt" else "."))
            print("               Waehrenddessen wird nicht gelaeutet.")
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
    """Was bei einem Doppelklick passiert.

    Das Menue bleibt stehen: Nach jedem Punkt kommt es zurueck, bis jemand 0
    waehlt oder das Fenster schliesst. Vorher endete das Programm nach einer
    einzigen Aktion - wer nach dem Status noch einen Testlauf wollte, musste
    die Programmdatei erneut oeffnen.
    """
    while True:
        rc = _menue_einmal()
        if rc is None:          # 0 oder Fenster zu
            return 0
        if rc == IM_ANDEREN_FENSTER:
            # Dort steht gleich dasselbe Menue - mit Adminrechten.
            try:
                input("\nDieses Fenster kann zu. Eingabetaste ...")
            except (EOFError, KeyboardInterrupt):
                pass
            return 0
        try:
            input("\nWeiter mit der Eingabetaste ...")
        except (EOFError, KeyboardInterrupt):
            return rc
        print()
        print()


def _menue_einmal() -> int | None:
    """Zeigt das Menue und fuehrt EINEN Punkt aus.

    Gibt None zurueck, wenn Schluss ist (Punkt 0 oder geschlossenes Fenster),
    sonst den Rueckgabewert der Aktion.
    """
    print(f"Glockensteuerung-Gateway {pfade.version()}")
    print("=" * 56)
    if ist_windows():
        # Bei jedem Durchgang frisch: Nach "anhalten" soll hier auch
        # "angehalten" stehen, nicht der Stand von vor fuenf Minuten.
        print(f"Dienst: {windienst.zustand()}")
    if not pfade.env_datei():
        print("Noch nicht eingerichtet - dafuer ist Punkt 1 da.")
    print()
    print(" 1  Installieren: Ordner, Zugangsdaten und Dienst einrichten")
    print(" 2  Einstellungen (Zugang, Simulation, Ruhezeit, E-Mail, Geraet)")
    print(" 3  Status und Protokoll ansehen")
    print(" 4  Testlauf im Fenster (loest NICHTS aus)")
    print(" 5  Verbindung pruefen (Zertifikate)")
    print(" 6  Dienst neu starten")
    print(" 7  Dienst anhalten (noetig, um die Programmdatei zu ersetzen)")
    print(" 8  Dienst wieder entfernen")
    print(" 0  Schliessen")
    print()
    try:
        wahl = input("Auswahl: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
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
        rc = anhalten()
    elif wahl == "8":
        rc = entfernen()
    elif wahl in ("0", ""):
        return None
    else:
        print(f"'{wahl}' kenne ich nicht - bitte eine Zahl von 0 bis 8.")
        rc = 0
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
    ap.add_argument("--anhalten", action="store_true",
                    help="Dienst anhalten (um die Programmdatei zu ersetzen)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--protokoll", action="store_true")
    ap.add_argument("--testlauf", action="store_true", help="Laeuft im Fenster, loest NICHTS aus")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--warten", action="store_true",
                    help="Am Ende auf eine Taste warten (fuer das UAC-Fenster)")
    args = ap.parse_args(argv)

    _eigene_module_schuetzen()
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
    elif args.anhalten:
        rc = anhalten()
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
        # Das erhoehte Fenster hat seine Aufgabe erledigt - und bleibt jetzt
        # offen, mit dem Menue. Dort gelten Adminrechte, die Punkte 1, 6, 7
        # und 8 fragen also nicht noch einmal nach. Vorher schloss es sich
        # nach der einen Aktion, und fuer die naechste ging alles von vorn los.
        try:
            input("\nWeiter mit der Eingabetaste ...")
        except (EOFError, KeyboardInterrupt):
            return rc
        print()
        print()
        return menue()
    return rc


if __name__ == "__main__":
    sys.exit(main())
