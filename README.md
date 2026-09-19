# Glockensteuerung: ChurchTools ⇄ VOCO-futura ST5

Automatisches Glockenläuten aus **ChurchTools**: Das passende Läuteprogramm der
Läutesteuerung **HEW VOCO-futura ST5** wird zur Termin-Zeit ausgelöst – die
manuelle Programmwahl entfällt. Bedienung und Konfiguration laufen als
**ChurchTools-Extension**.

> **📖 Vollständige Einrichtung: [`ANLEITUNG.md`](ANLEITUNG.md)**

---

## Aufbau

| Teil | Was | Läuft |
|---|---|---|
| **[`extension/`](extension/)** | ChurchTools-Modul (Vue 3 + Vite): Status, manuell läuten, Regeln pflegen | im Browser, in ChurchTools |
| **[`gateway/`](gateway/)** | Python-Dienst: löst Programme **automatisch** zur Termin-Zeit aus | auf einem dauerhaft laufenden Rechner mit Internet — unter Windows als [fertige Programmdatei](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest) und echter Dienst |

```
  ChurchTools-Extension ──┐   Regeln + Gerät        ┌── Gateway-Dienst
  (Browser, Bedienung)    │  (im ChurchTools-Store)  │   (dauerhaft, überall)
                          └──────────┬───────────────┘
                                     │  MQTT über WebSocket
                        hew-voco.de:8084  →  VOCO-futura ST5  →  🔔
```

- **Manuelles** Läuten aus ChurchTools braucht **keinen** Gateway (läuft im Browser).
- **Automatik** braucht den Gateway – der muss **nicht** in der Kirche stehen
  (Raspberry Pi, kleiner Server/VPS oder Dauer-PC). ChurchTools selbst kann keine
  Hintergrund-Aufgaben ausführen.
- Beide sprechen den HEW-Broker per MQTT – Protokoll:
  [`docs/VOCO-MQTT-Protokoll.md`](docs/VOCO-MQTT-Protokoll.md).

## Kompatibilität

- ✅ **Aktuell:** **HEW VOCO-futura** (z. B. ST5, mit LAN/WLAN-Modul und
  `hew-voco.de`-Portal).
- 🔜 **Geplant:** weitere HEW-Systeme und Steuerungen **anderer Hersteller**.
- 🔜 **Später:** eine **universelle**, herstellerübergreifende Lösung.

## 🛡️ Simulationsmodus (kein versehentliches Läuten)

Zum Einrichten und Testen, ohne dass wirklich geläutet wird:

- **Extension:** startet immer im **Simulationsmodus** – „Läuten“ sendet nichts,
  sondern zeigt im **Ereignis-Log**, was passieren *würde* (und die echten
  Antworten der Anlage). Erst nach bewusstem Ausschalten wird real geläutet.
- **Gateway:** `Glockensteuerung-Gateway.exe --testlauf` (bzw.
  `python scheduler.py --dry-run`) – oder dauerhaft `VOCO_SIMULATION=1`, was die
  Einrichtung beim ersten Mal von selbst vorschlägt.

## Download (bleibt immer gleich)

Diese drei Links liefern stets die **neueste** veröffentlichte Fassung – sie
ändern sich nie, auch nicht mit der Version:

| Was | Link |
|---|---|
| Erweiterung für ChurchTools | [`glockensteuerung.zip`](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest/download/glockensteuerung.zip) |
| Gateway-Dienst für Windows (fertig gebaut) | [`Glockensteuerung-Gateway.exe`](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest/download/Glockensteuerung-Gateway.exe) |
| Gateway-Dienst als Quelltext (Linux, eigenes Python) | „Source code" im [neuesten Release](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest) – der Ordner `gateway/` steckt darin |

Welche Version dahintersteckt, sagt der Titel des
[neuesten Releases](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest).

## Schnellstart

1. **Extension bauen:** GitHub-Actions-Workflow „ChurchTools-Extension bauen“
   ausführen (liefert die ZIP), oder lokal `cd extension && npm run deploy`.
2. **In ChurchTools hochladen:** Admin → Erweiterungen → ZIP installieren.
3. **Gerät + Regeln** im Modul „Glockensteuerung“ eintragen (Simulation an lassen).
4. **Gateway** auf einem Dauer-Rechner einrichten: unter Windows die
   Programmdatei oben herunterladen, neben die `.env` legen, Doppelklick, „1“.
   Vorher mit `--testlauf` prüfen, ohne dass etwas läutet.
5. Passt alles: Simulation aus → scharf.

→ Details: **[`ANLEITUNG.md`](ANLEITUNG.md)**

## Projektstruktur

```
extension/   ChurchTools-Extension (Vue 3 + Vite)
gateway/     Python-Dienst (Automatik + MQTT)
docs/        VOCO-MQTT-Protokoll.md · mockup/ (Design) · handbuch/ (HEW-Handbücher)
ANLEITUNG.md Schritt-für-Schritt-Anleitung
.github/scripts/  release.sh (Release je Version) · changelog.sh
```

## Changelog-Zeile je Commit

Die Release-Beschreibungen werden automatisch gebaut. Damit dort Sätze stehen,
die eine Gemeinde versteht – und nicht Commit-Betreffe –, bekommt jeder Commit
mit sichtbarer Wirkung am Ende eine Zeile:

```
Changelog: <Art> | <Bereich> | <Satz für Anwender>
```

- **Art:** `Verbesserung`, `Fehler` oder `Löschung`
- **Bereich:** entscheidet zugleich, in welchen **Teil** der Eintrag kommt:

  | Teil | Bereiche |
  |---|---|
  | Gateway (Dienst auf dem Rechner) | `Automatik`, `Gateway`, `Dienst`, `Installation`, `E-Mail`, `Postausgang` |
  | Erweiterung (in ChurchTools) | alles andere, z. B. `Steuerung`, `Gerät`, `Regeln`, `Allgemein` |

  Die Release-Beschreibung führt beide Teile getrennt auf, und das Fenster
  „Was ist neu" in ChurchTools zeigt nur den Teil der Erweiterung. Ein neuer
  Bereich, der zum Gateway gehört, muss in `changelog.sh` ergänzt werden –
  sonst landet er beim falschen Teil.
- **Satz:** was sich für die Anwender ändert, nicht was am Code geschah

Beispiel:

```
Changelog: Fehler | Gateway | Serientermine wurden mit dem Serienbeginn geplant und lösten deshalb nie aus.
```

Mehrere Zeilen je Commit sind erlaubt. Commits ohne solche Zeile – CI-Anpassungen,
Refactorings – tauchen im Changelog nicht auf; das ist Absicht. Vor dem Öffnen
eines Pull Requests lässt sich der Changelog vorab ansehen:

```bash
.github/scripts/changelog.sh HEAD origin/main
```

## Versionsnummern

`<Jahr>.<Mittelstelle>.<Patch>[.<Hotfix>]`, vergeben beim Merge auf `main`:

| Stand | nächste Version | wann |
|---|---|---|
| 26.8.5 | **26.8.6** | irgendeine Neuerung |
| 26.6.9 | **26.7.0** | der Patch läuft nur bis 9 |
| 26.9.9 | **26.10.0** | die Mittelstelle zählt unbegrenzt weiter |
| 26.8.9 | **26.8.9.1** | nur behobene Fehler → vierte Stelle |
| 26.8.9.1 | **26.8.9.2** | weitere Korrektur |
| 26.8.9.2 | **26.9.0** | wieder eine Neuerung |
| 26.8.3 | **26.9.0** | `Version-Sprung: Mittelstelle` in der Merge-Nachricht |

Ob eine Fassung „nur behobene Fehler" bringt, entscheidet `changelog.sh --art`
an den Changelog-Zeilen – dieselbe Stelle, die auch über Ergänzen oder Ersetzen
des Changelogs entscheidet. Zwei Stellen, die dasselbe unterschiedlich
beantworten, wären eine sichere Fehlerquelle.

Eine **Korrektur** ergänzt den Changelog der letzten Funktionsversion, eine
**Neuerung** fängt ihn frisch an – das entscheidet `changelog.sh` selbst anhand
der Art der Einträge. Kommen dadurch mehrere Fassungen zusammen, steht **jede
unter ihrer eigenen Nummer**; bei einer einzelnen entfällt die Überschrift, denn
welche das ist, sagt der Titel des Release.

In der Release-Beschreibung steht nur der Changelog; was welche Datei tut,
steht hier und nicht in jeder Version aufs Neue. Kommt eine Datei dazu oder
fällt eine weg, steht das unter `## Dateien` – nur dann.

## Dokumentation gehört zum Pull Request

Wer etwas ändert, prüft im selben Pull Request, ob die Markdown-Dateien noch
stimmen, und zieht sie mit:

| Datei | Wofür |
|---|---|
| [`ANLEITUNG.md`](ANLEITUNG.md) | Schritt für Schritt für die Gemeinde |
| [`README.md`](README.md) | Überblick, Downloads, Arbeitsweise |
| [`gateway/README.md`](gateway/README.md) | Betrieb des Dienstes, Dateien, Fehlersuche |
| [`extension/README.md`](extension/README.md) | Modul, Rechte, Entwicklung |
| [`docs/`](docs/) | VOCO-Protokoll und ChurchTools-API |

Besonders leicht veralten Dinge, die nur *nebenbei* mitwandern: Menüpunkte mit
Nummern, Dateinamen, Schalter auf der Kommandozeile, Rechte-Tabellen. Eine
Anleitung, die einmal in die Irre führt, kostet mehr Zeit als das Nachziehen
gekostet hätte.

## 🔐 Sicherheit

- Geräte-Passwort, ChurchTools-Token & Login-Daten sind **Geheimnisse** – niemals
  ins Repository. Lokal nur in `.env` (per `.gitignore` ausgeschlossen).
- **Modulzugriff einschränken: Wer das Modul öffnen kann, kann läuten.** Welche
  Rechte es gibt, was sie bewirken und wie man sie vergibt, steht in
  [`ANLEITUNG.md`, Teil 4](ANLEITUNG.md#teil-4--wer-darf-was-rechte-in-churchtools).

## Hinweise

- Kein offizielles Produkt der Herforder Elektromotoren-Werke (HEW). Die
  MQTT-Anbindung wurde aus dem öffentlichen Web-Client der VOCO-futura abgeleitet.
  Für dauerhaften Betrieb – besonders bei mehreren Gemeinden – empfiehlt sich eine
  offizielle Freigabe/Schnittstelle von HEW.
