#!/usr/bin/env python3
"""
Ersteinrichtung im Fenster: fragt, was gebraucht wird, und legt die .env an.

Bis hierher musste die Konfigurationsdatei von Hand geschrieben werden - mit
dem richtigen Namen (".env", nicht ".env.txt"), am richtigen Ort und mit
Schluesselwoertern, die niemand auswendig kennt. Das ist der Punkt, an dem eine
frische Installation scheitert, lange bevor irgendetwas laeutet.

Deshalb hier ein gefuehrter Ablauf: fragen, gleich ausprobieren, dann erst
schreiben. Wer sich vertippt, erfaehrt es sofort und nicht erst, wenn am
Sonntag die Glocken schweigen.

Eine vorhandene .env wird nicht ueberschrieben, sondern als Vorgabe angeboten:
Eingabetaste behaelt den bisherigen Wert.
"""
from __future__ import annotations
import os

import pfade

# Was in die .env geschrieben wird. Die Reihenfolge ist die der Fragen.
VORLAGE = """# Zugangsdaten der Glockensteuerung. Diese Datei gehoert NICHT ins Internet
# und nicht in ein Repository - sie ist der Schluessel zu ChurchTools.
#
# Angelegt von Glockensteuerung-Gateway.exe (Menuepunkt "Einrichten").

# Adresse der eigenen ChurchTools-Instanz
CT_BASE_URL={base}

# Login-Token eines technischen Benutzers
# (ChurchTools: Persoenliche Einstellungen -> Sicherheit -> Login-Token)
CT_LOGIN_TOKEN={token}

# Simulation: 1 = es wird NICHTS ausgeloest, nur protokolliert.
VOCO_SIMULATION={simulation}
{zusatz}"""


def _frage(text: str, vorgabe: str = "", geheim: bool = False) -> str:
    """Eine Frage stellen. Leere Eingabe behaelt die Vorgabe."""
    if vorgabe:
        gezeigt = (vorgabe[:4] + "…" + vorgabe[-4:]) if geheim and len(vorgabe) > 10 else vorgabe
        text = f"{text}\n   [{gezeigt}] "
    else:
        text = f"{text}\n   "
    try:
        eingabe = input(text).strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAbgebrochen - es wurde nichts geaendert.")
    return eingabe or vorgabe


def _ja(text: str, standard: bool = True) -> bool:
    antwort = _frage(f"{text} ({'J/n' if standard else 'j/N'})").strip().lower()
    if not antwort:
        return standard
    return antwort[0] in ("j", "y")


def _pruefe_churchtools(base: str, token: str) -> tuple[bool, str]:
    """Gleich ausprobieren: Stimmen Adresse und Token?

    Der Unterschied zwischen "falsch abgetippt" und "geht nicht" soll hier
    fallen, nicht erst im Dauerbetrieb.
    """
    from churchtools import ChurchTools
    try:
        ct = ChurchTools(base, token)
    except Exception as e:
        return False, f"Anmeldung fehlgeschlagen: {e}"

    try:
        module = ct.get("/custommodules")
        namen = {m.get("shorty") for m in module or []}
        if "glockensteuerung" not in namen:
            return True, ("Angemeldet - aber das Modul 'glockensteuerung' ist in "
                          "ChurchTools noch nicht vorhanden. Es entsteht, sobald "
                          "die Erweiterung dort einmal geoeffnet wurde.")
    except Exception as e:
        return True, f"Angemeldet - die Modulliste war aber nicht lesbar ({e})."

    try:
        from config import load_from_churchtools
        cfg = load_from_churchtools(ct)
    except Exception as e:
        return True, f"Angemeldet - die Konfiguration war nicht lesbar ({e})."

    if not cfg.device:
        return True, ("Angemeldet - in der Erweiterung ist aber noch kein Geraet "
                      "hinterlegt (Seriennummer und Geraetepasswort).")
    aktiv = len([r for r in cfg.rules if r.active and r.pgs_name])
    return True, (f"Angemeldet. Geraet {cfg.device.serial} gefunden, "
                  f"{aktiv} aktive Regel(n).")


def _vorhandene_werte() -> dict[str, str]:
    """Liest die vorhandene .env - ohne sie in die Umgebung zu uebernehmen."""
    werte: dict[str, str] = {}
    pfad = pfade.env_datei()
    if not pfad:
        return werte
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if zeile and not zeile.startswith("#") and "=" in zeile:
                    k, v = zeile.split("=", 1)
                    werte[k.strip()] = v.strip()
    except Exception:
        pass
    return werte


def _zusatz_erhalten(werte: dict[str, str]) -> str:
    """Alles, was die Vorlage nicht kennt, bleibt erhalten.

    In der .env koennen Dinge stehen, nach denen hier niemand fragt - der
    Postausgang fuer Fehlermeldungen, eine Ruhezeit, ein eigenes
    Zertifikatsbuendel. Die gingen sonst beim Einrichten verloren.
    """
    bekannt = {"CT_BASE_URL", "CT_LOGIN_TOKEN", "CT_API_TOKEN", "VOCO_SIMULATION"}
    uebrig = [f"{k}={v}" for k, v in werte.items() if k not in bekannt]
    if not uebrig:
        return ""
    return "\n# Uebernommen aus der bisherigen Einrichtung:\n" + "\n".join(uebrig) + "\n"


def assistent() -> bool:
    """Fuehrt durch die Einrichtung. Gibt zurueck, ob eine .env vorliegt."""
    werte = _vorhandene_werte()
    pfad = pfade.env_datei() or os.path.join(pfade.programmordner(), pfade.ENV_DATEI)

    print()
    print("Einrichtung der Glockensteuerung")
    print("=" * 56)
    if werte:
        print(f"Es gibt bereits eine Konfiguration: {pfad}")
        print("Die Eingabetaste behaelt den jeweils gezeigten Wert.")
    else:
        print("Zwei Angaben werden gebraucht. Beide stehen in ChurchTools.")
    print()

    base = _frage("1. Adresse von ChurchTools (z. B. https://gemeinde.church.tools)",
                  werte.get("CT_BASE_URL", ""))
    if not base.startswith("http"):
        base = "https://" + base
    base = base.rstrip("/")

    print()
    print("   Der Login-Token gehoert zu einem technischen Benutzer.")
    print("   In ChurchTools: Persoenliche Einstellungen -> Sicherheit -> Login-Token.")
    token = _frage("2. Login-Token",
                   werte.get("CT_LOGIN_TOKEN") or werte.get("CT_API_TOKEN", ""), geheim=True)
    if not base or not token:
        print("\nOhne Adresse und Token kann der Dienst nichts tun. Abgebrochen.")
        return False

    print()
    print("Verbindung wird geprueft ...")
    ok, meldung = _pruefe_churchtools(base, token)
    print(f"   {meldung}")
    if not ok:
        print()
        if not _ja("Trotzdem so speichern?", standard=False):
            print("Abgebrochen - es wurde nichts geaendert.")
            return False

    print()
    bisher_sim = werte.get("VOCO_SIMULATION", "1").strip().lower() in ("1", "true", "yes", "on")
    print("   In der Simulation plant der Dienst alles, loest aber NICHTS aus.")
    print("   Fuer den ersten Lauf ist das die sichere Wahl.")
    simulation = _ja("3. Simulation einschalten?", standard=bisher_sim)

    inhalt = VORLAGE.format(base=base, token=token,
                            simulation="1" if simulation else "0",
                            zusatz=_zusatz_erhalten(werte))
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(inhalt)
    except Exception as e:
        print(f"\nDie Datei konnte nicht geschrieben werden: {e}")
        print(f"Erwartet wurde: {pfad}")
        return False

    print()
    print(f"Gespeichert: {pfad}")
    if simulation:
        print("Der Dienst laeuft in Simulation - er loest nichts aus. Zum Scharfschalten")
        print("spaeter in dieser Datei VOCO_SIMULATION=0 setzen oder hier erneut einrichten.")
    return True
