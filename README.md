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
| **[`gateway/`](gateway/)** | Python-Dienst: löst Programme **automatisch** zur Termin-Zeit aus | auf einem dauerhaft laufenden Rechner mit Internet |

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

## 🛡️ Simulationsmodus (kein versehentliches Läuten)

Zum Einrichten und Testen, ohne dass wirklich geläutet wird:

- **Extension:** startet immer im **Simulationsmodus** – „Läuten“ sendet nichts,
  sondern zeigt im **Ereignis-Log**, was passieren *würde* (und die echten
  Antworten der Anlage). Erst nach bewusstem Ausschalten wird real geläutet.
- **Gateway:** `python scheduler.py --dry-run` bzw. dauerhaft `VOCO_SIMULATION=1`.

## Schnellstart

1. **Extension bauen:** GitHub-Actions-Workflow „ChurchTools-Extension bauen“
   ausführen (liefert die ZIP), oder lokal `cd extension && npm run deploy`.
2. **In ChurchTools hochladen:** Admin → Erweiterungen → ZIP installieren.
3. **Gerät + Regeln** im Modul „Glockensteuerung“ eintragen (Simulation an lassen).
4. **Gateway** auf einem Dauer-Rechner einrichten, mit `--dry-run` testen.
5. Passt alles: Simulation aus → scharf.

→ Details: **[`ANLEITUNG.md`](ANLEITUNG.md)**

## Projektstruktur

```
extension/   ChurchTools-Extension (Vue 3 + Vite)
gateway/     Python-Dienst (Automatik + MQTT)
docs/        VOCO-MQTT-Protokoll.md, mockup/ (Design-Vorschau)
ANLEITUNG.md Schritt-für-Schritt-Anleitung
```

## 🔐 Sicherheit

- Geräte-Passwort, ChurchTools-Token & Login-Daten sind **Geheimnisse** – niemals
  ins Repository. Lokal nur in `.env` (per `.gitignore` ausgeschlossen).
- Modulzugriff in ChurchTools einschränken: Wer das Modul öffnen kann, kann läuten.

## Hinweise

- Kein offizielles Produkt der Herforder Elektromotoren-Werke (HEW). Die
  MQTT-Anbindung wurde aus dem öffentlichen Web-Client der VOCO-futura abgeleitet.
  Für dauerhaften Betrieb – besonders bei mehreren Gemeinden – empfiehlt sich eine
  offizielle Freigabe/Schnittstelle von HEW.
