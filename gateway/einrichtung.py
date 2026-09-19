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

# Was in der .env stehen kann - in der Reihenfolge, in der es dort landet.
# Der Kommentar wandert mit in die Datei: Wer sie spaeter oeffnet, soll lesen
# koennen, wozu eine Zeile gut ist, ohne im Quelltext nachzusehen.
FELDER: list[tuple[str, str]] = [
    ("CT_BASE_URL", "Adresse der eigenen ChurchTools-Instanz"),
    ("CT_LOGIN_TOKEN", "Login-Token eines technischen Benutzers\n"
                       "# (ChurchTools: Persoenliche Einstellungen -> Sicherheit -> Login-Token)"),
    ("VOCO_SIMULATION", "1 = es wird NICHTS ausgeloest, nur protokolliert"),
    ("VOCO_QUIET", "Ruhezeit, z. B. 22:00-06:00 - darin wird nie ausgeloest"),
    ("VOCO_AUTO_UPDATE", "1 = neue Fassungen selbst einspielen, wenn nichts laeutet"),
    ("VOCO_SERIAL", "Geraet: nur noetig, wenn es in der Erweiterung fehlt"),
    ("VOCO_DEVICE_PW", "Geraetepasswort (GEHEIM)"),
    ("SMTP_HOST", "Postausgang fuer Stoerungsmeldungen (die Erweiterung hat Vorrang)"),
    ("SMTP_PORT", "587 fuer STARTTLS, 465 fuer SSL"),
    ("SMTP_USER", "Benutzername am Postausgang"),
    ("SMTP_PASS", "Passwort am Postausgang (GEHEIM)"),
    ("SMTP_SSL", "1 = SSL (Port 465). Sonst STARTTLS"),
    ("EMAIL_FROM", "Absender. Leer = derselbe wie SMTP_USER"),
    ("EMAIL_TO", "Wer die Stoerungsmeldungen bekommt"),
    ("VOCO_CA_BUNDLE", "Eigenes Zertifikatsbuendel (bei Virenscanner/Firmen-Proxy)"),
]
BEKANNT = {name for name, _ in FELDER}
# Altnamen, die durch die Liste oben ersetzt werden.
VERALTET = {"CT_API_TOKEN"}


def _schreibe(werte: dict[str, str]) -> str:
    """Schreibt die .env. Leere Werte fallen weg, Unbekanntes bleibt erhalten.

    In der Datei koennen Dinge stehen, nach denen hier niemand fragt. Die
    gingen sonst beim naechsten Speichern verloren - deshalb wandern sie
    unveraendert ans Ende.
    """
    pfad = pfade.env_datei() or os.path.join(pfade.programmordner(), pfade.ENV_DATEI)
    zeilen = [
        "# Zugangsdaten der Glockensteuerung. Diese Datei gehoert NICHT ins Internet",
        "# und nicht in ein Repository - sie ist der Schluessel zu ChurchTools.",
        "#",
        "# Gepflegt ueber Glockensteuerung-Gateway.exe, Menuepunkt \"Einstellungen\".",
        "",
    ]
    for name, hinweis in FELDER:
        wert = (werte.get(name) or "").strip()
        if not wert:
            continue
        zeilen.append(f"# {hinweis}")
        zeilen.append(f"{name}={wert}")
        zeilen.append("")
    uebrig = [f"{k}={v}" for k, v in werte.items()
              if k not in BEKANNT and k not in VERALTET and (v or "").strip()]
    if uebrig:
        zeilen.append("# Weitere Einstellungen, unveraendert uebernommen:")
        zeilen.extend(uebrig)
        zeilen.append("")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen))
    return pfad


def _frage(text: str, vorgabe: str = "", geheim: bool = False) -> str:
    """Eine Frage stellen. Leere Eingabe behaelt die Vorgabe, "-" loescht sie.

    Das Minus ist noetig, weil sonst kein einmal gesetzter Wert mehr wegzubekommen
    waere: Die Eingabetaste bedeutet ja "so lassen". Wer eine Ruhezeit wieder
    abschaffen will, stuende sonst vor einer Sackgasse.
    """
    if vorgabe:
        gezeigt = (vorgabe[:4] + "…" + vorgabe[-4:]) if geheim and len(vorgabe) > 10 else vorgabe
        text = f"{text}\n   [{gezeigt}]  (Eingabetaste = so lassen, - = loeschen) "
    else:
        text = f"{text}\n   "
    try:
        eingabe = input(text).strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAbgebrochen - es wurde nichts geaendert.")
    if eingabe == "-":
        return ""
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


def zugangsdaten(werte: dict[str, str] | None = None) -> bool:
    """Fragt Adresse und Token ab und prueft sie gleich.

    Gibt zurueck, ob danach eine brauchbare Konfiguration vorliegt.
    """
    werte = _vorhandene_werte() if werte is None else werte

    print()
    print("Zugang zu ChurchTools")
    print("-" * 56)
    if werte.get("CT_BASE_URL"):
        print("Die Eingabetaste behaelt den jeweils gezeigten Wert.")
    else:
        print("Zwei Angaben werden gebraucht. Beide stehen in ChurchTools.")
    print()

    base = _frage("1. Adresse von ChurchTools (z. B. https://gemeinde.church.tools)",
                  werte.get("CT_BASE_URL", ""))
    if base and not base.startswith("http"):
        base = "https://" + base
    base = base.rstrip("/")

    print()
    print("   Der Login-Token gehoert zu einem technischen Benutzer.")
    print("   In ChurchTools: Persoenliche Einstellungen -> Sicherheit -> Login-Token.")
    token = _frage("2. Login-Token",
                   werte.get("CT_LOGIN_TOKEN") or werte.get("CT_API_TOKEN", ""), geheim=True)
    if not base or not token:
        print("\nOhne Adresse und Token kann der Dienst nichts tun. Abgebrochen.")
        return bool(pfade.env_datei())

    print()
    print("Verbindung wird geprueft ...")
    ok, meldung = _pruefe_churchtools(base, token)
    print(f"   {meldung}")
    if not ok and not _ja("Trotzdem so speichern?", standard=False):
        print("Abgebrochen - es wurde nichts geaendert.")
        return bool(pfade.env_datei())

    werte["CT_BASE_URL"] = base
    werte["CT_LOGIN_TOKEN"] = token
    werte.pop("CT_API_TOKEN", None)
    if "VOCO_SIMULATION" not in werte:
        print()
        print("   In der Simulation plant der Dienst alles, loest aber NICHTS aus.")
        print("   Fuer den ersten Lauf ist das die sichere Wahl.")
        werte["VOCO_SIMULATION"] = "1" if _ja("Simulation einschalten?", standard=True) else "0"
    pfad = _schreibe(werte)
    print(f"\nGespeichert: {pfad}")
    return True


def _simulation(werte: dict[str, str]) -> None:
    an = _ist_an(werte.get("VOCO_SIMULATION", "1"))
    print()
    print(f"Simulation ist zurzeit {'EIN' if an else 'AUS'}.")
    print("Bei eingeschalteter Simulation plant der Dienst alles, loest aber NICHTS aus.")
    werte["VOCO_SIMULATION"] = "1" if _ja("Simulation einschalten?", standard=an) else "0"
    if werte["VOCO_SIMULATION"] == "0":
        print("ACHTUNG: Ab jetzt wird echt gelaeutet.")
    _schreibe(werte)


def _selbstaktualisierung(werte: dict[str, str]) -> None:
    an = _ist_an(werte.get("VOCO_AUTO_UPDATE", "1"))
    print()
    print(f"Selbstaktualisierung ist zurzeit {'EIN' if an else 'AUS'}.")
    print("Eingeschaltet holt sich der Dienst neue Fassungen selbst - aber nur,")
    print("wenn eine davon ihn betrifft, und nur, wenn gerade nichts laeutet und")
    print("in der naechsten halben Stunde nichts ansteht. Der Neustart dauert")
    print("Sekunden; die Erweiterung weiss davon und meldet keine Stoerung.")
    werte["VOCO_AUTO_UPDATE"] = "1" if _ja("Selbstaktualisierung einschalten?", standard=an) else "0"
    _schreibe(werte)


def _ruhezeit(werte: dict[str, str]) -> None:
    print()
    print("In der Ruhezeit wird NIE ausgeloest - auch nicht, wenn ein Termin es")
    print("verlangt. Schreibweise: 22:00-06:00. Leer lassen = keine Ruhezeit.")
    wert = _frage("Ruhezeit", werte.get("VOCO_QUIET", "")).strip()
    if wert and not _ruhezeit_gueltig(wert):
        print("Das ist keine gueltige Angabe (erwartet: 22:00-06:00). Unveraendert.")
        return
    werte["VOCO_QUIET"] = wert
    _schreibe(werte)
    print("Keine Ruhezeit mehr." if not wert else f"Ruhezeit: {wert}")


def _ruhezeit_gueltig(wert: str) -> bool:
    import datetime as dt
    if "-" not in wert:
        return False
    a, b = wert.split("-", 1)
    try:
        dt.time.fromisoformat(a.strip())
        dt.time.fromisoformat(b.strip())
        return True
    except Exception:
        return False


def _email(werte: dict[str, str]) -> None:
    print()
    print("Postausgang fuer Stoerungsmeldungen")
    print("-" * 56)
    print("Der Dienst meldet Stoerungen per E-Mail. Sind die Zugangsdaten in der")
    print("Erweiterung hinterlegt (Untermenue \"E-Mail-Versand\"), haben die Vorrang -")
    print("das hier ist der Ersatzweg fuer einen Rechner ohne solche Pflege.")
    print("Host leer lassen = keine E-Mails, es bleibt beim Protokoll.")
    print()
    host = _frage("Postausgangsserver (z. B. smtp.example.de)", werte.get("SMTP_HOST", "")).strip()
    if not host:
        for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS",
                     "SMTP_SSL", "EMAIL_FROM", "EMAIL_TO"):
            werte[name] = ""
        _schreibe(werte)
        print("E-Mail-Versand ausgeschaltet.")
        return

    ssl_an = _ist_an(werte.get("SMTP_SSL", "0"))
    ssl_an = _ja("Verschluesselung ueber SSL (Port 465)? Nein = STARTTLS (Port 587)",
                 standard=ssl_an)
    vorgabe_port = werte.get("SMTP_PORT") or ("465" if ssl_an else "587")
    port = _frage("Port", vorgabe_port).strip()
    benutzer = _frage("Benutzername", werte.get("SMTP_USER", "")).strip()
    passwort = _frage("Passwort", werte.get("SMTP_PASS", ""), geheim=True)
    absender = _frage("Absender (leer = Benutzername)", werte.get("EMAIL_FROM", "")).strip()
    empfaenger = _frage("Empfaenger der Meldungen", werte.get("EMAIL_TO", "")).strip()

    werte.update({
        "SMTP_HOST": host, "SMTP_PORT": port, "SMTP_USER": benutzer,
        "SMTP_PASS": passwort, "SMTP_SSL": "1" if ssl_an else "",
        "EMAIL_FROM": absender, "EMAIL_TO": empfaenger,
    })
    _schreibe(werte)
    print("Gespeichert.")

    if _ja("Gleich eine Testmail schicken?", standard=True):
        _testmail(werte)


def _testmail(werte: dict[str, str]) -> None:
    """Einmal wirklich verschicken - sonst faellt ein Tippfehler erst im Ernstfall auf."""
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS",
                 "SMTP_SSL", "EMAIL_FROM", "EMAIL_TO"):
        if werte.get(name):
            os.environ[name] = werte[name]
        else:
            os.environ.pop(name, None)
    try:
        from notify import EmailNotifier
        notifier = EmailNotifier()
        if not notifier.enabled:
            print("Kein Postausgang eingerichtet - es wurde nichts verschickt.")
            return
        ok = notifier.notify("Glockensteuerung: Testmail",
                             "Diese Nachricht bestaetigt, dass der Gateway Mails "
                             "verschicken kann.")
        print("Testmail verschickt." if ok else
              "Die Testmail ging NICHT raus. Bitte Server, Port, Benutzer und "
              "Passwort pruefen.")
    except Exception as e:
        print(f"Die Testmail ging nicht raus: {e}")


def _geraet(werte: dict[str, str]) -> None:
    print()
    print("Geraet (Ersatzweg)")
    print("-" * 56)
    print("Normalerweise stehen Seriennummer und Passwort in der Erweiterung, und")
    print("der Dienst liest sie von dort. Hier eintragen muss man sie nur, wenn")
    print("das nicht moeglich ist. Leer lassen = aus der Erweiterung nehmen.")
    print()
    serie = _frage("Seriennummer (z. B. VH-000000)", werte.get("VOCO_SERIAL", "")).strip()
    passwort = _frage("Geraetepasswort", werte.get("VOCO_DEVICE_PW", ""), geheim=True)
    werte["VOCO_SERIAL"] = serie
    werte["VOCO_DEVICE_PW"] = passwort
    _schreibe(werte)
    print("Gespeichert." if serie else "Eintrag geleert - es gilt die Erweiterung.")


def _zertifikat(werte: dict[str, str]) -> None:
    print()
    print("Eigenes Zertifikatsbuendel")
    print("-" * 56)
    print("Nur noetig, wenn ein Virenscanner oder eine Firmen-Firewall die")
    print("Verbindung aufbricht. Welches Zertifikat gebraucht wird, sagt die")
    print("Verbindungspruefung (Menuepunkt \"Verbindung pruefen\").")
    print("Leer lassen = die Zertifikate des Systems benutzen.")
    print()
    pfad = _frage("Pfad zur PEM-Datei", werte.get("VOCO_CA_BUNDLE", "")).strip()
    if pfad and not os.path.exists(pfad):
        print(f"Die Datei gibt es nicht: {pfad}")
        if not _ja("Trotzdem eintragen?", standard=False):
            return
    werte["VOCO_CA_BUNDLE"] = pfad
    _schreibe(werte)
    print("Gespeichert." if pfad else "Eintrag geleert.")


def _ist_an(wert: str) -> bool:
    return (wert or "").strip().lower() in ("1", "true", "yes", "on", "ja")


def _zustand(werte: dict[str, str]) -> list[str]:
    """Kurzfassung fuer das Menue - was ist eingestellt, was nicht?"""
    ct = werte.get("CT_BASE_URL", "")
    mail = werte.get("SMTP_HOST", "")
    return [
        f"ChurchTools:  {ct or '(nicht eingerichtet)'}",
        f"Simulation:   {'EIN - es wird nichts ausgeloest' if _ist_an(werte.get('VOCO_SIMULATION', '1')) else 'AUS - es wird echt gelaeutet'}",
        f"Ruhezeit:     {werte.get('VOCO_QUIET') or '(keine)'}",
        f"E-Mail:       {mail or '(aus)'}",
        f"Geraet:       {werte.get('VOCO_SERIAL') or '(aus der Erweiterung)'}",
        f"Zertifikat:   {werte.get('VOCO_CA_BUNDLE') or '(die des Systems)'}",
        f"Selbstaktualisierung: {'ein' if _ist_an(werte.get('VOCO_AUTO_UPDATE', '1')) else 'aus'}",
    ]


def einstellungen() -> bool:
    """Menue fuer alles, was frueher von Hand in die .env geschrieben wurde.

    Gibt zurueck, ob eine brauchbare Konfiguration vorliegt.
    """
    while True:
        werte = _vorhandene_werte()
        print()
        print("Einstellungen")
        print("=" * 56)
        for zeile in _zustand(werte):
            print("  " + zeile)
        print()
        print(" 1  Zugang zu ChurchTools (Adresse, Token)")
        print(" 2  Simulation ein- oder ausschalten")
        print(" 3  Ruhezeit")
        print(" 4  E-Mail-Versand (Stoerungsmeldungen)")
        print(" 5  Geraet (nur als Ersatz zur Erweiterung)")
        print(" 6  Eigenes Zertifikatsbuendel")
        print(" 7  Selbstaktualisierung ein- oder ausschalten")
        print(" 0  Zurueck")
        print()
        try:
            wahl = input("Auswahl: ").strip()
        except (EOFError, KeyboardInterrupt):
            return bool(pfade.env_datei())
        if wahl == "1":
            zugangsdaten(werte)
        elif wahl == "2":
            _simulation(werte)
        elif wahl == "3":
            _ruhezeit(werte)
        elif wahl == "4":
            _email(werte)
        elif wahl == "5":
            _geraet(werte)
        elif wahl == "6":
            _zertifikat(werte)
        elif wahl == "7":
            _selbstaktualisierung(werte)
        else:
            return bool(pfade.env_datei())


def assistent() -> bool:
    """Ersteinrichtung: ohne Konfiguration gleich fragen, sonst ins Menue."""
    if not pfade.env_datei():
        print()
        print("Einrichtung der Glockensteuerung")
        print("=" * 56)
        print("Es fehlen noch die Zugangsdaten.")
        if not zugangsdaten({}):
            return False
        print()
        print("Alles Weitere - Ruhezeit, E-Mail, Geraet - steht im Menue")
        print("\"Einstellungen\" bereit und kann jederzeit nachgetragen werden.")
        return True
    return einstellungen()
