# Glockensteuerung: ChurchTools ⇄ VOCO-futura ST5

Automatisches Läuten aus ChurchTools: Das passende Läuteprogramm der
**HEW VOCO-futura ST5** wird zur Termin-Zeit ausgelöst – ohne manuelle
Programmwahl. Bedienung und Einstellungen laufen als **ChurchTools-Extension**.

> **📖 Ausführliche Schritt-für-Schritt-Anleitung: [`ANLEITUNG.md`](ANLEITUNG.md)**

---

## In Kürze

Das Projekt besteht aus zwei Teilen:

| Teil | Was | Wo läuft es |
|---|---|---|
| **[`extension/`](extension/)** | ChurchTools-Modul: Status, manuell läuten, Regeln pflegen | im Browser (in ChurchTools) |
| **[`gateway/`](gateway/)** | löst Programme **automatisch** zur Termin-Zeit aus | ein Rechner mit Internet, der **dauerhaft läuft** |

```
  ChurchTools-Extension ──┐   Regeln + Gerät        ┌── Gateway-Dienst
  (Browser, Bedienung)    │  (im ChurchTools-Store)  │   (dauerhaft, überall)
                          └──────────┬───────────────┘
                                     │  MQTT über WebSocket
                        hew-voco.de:8084  →  VOCO-futura ST5  →  🔔
```

- **Manuell** läuten aus ChurchTools braucht **keinen** Gateway (läuft im Browser).
- **Automatik** braucht den Gateway – dieser muss **nicht** in der Kirche stehen
  (Raspberry Pi, kleiner Server/VPS oder Dauer-PC, egal wo). ChurchTools selbst
  kann keine Hintergrund-Aufgaben ausführen.

## 🛡️ Sicherheit: Simulationsmodus (kein versehentliches Läuten)

Zum Einrichten und Testen, **ohne** dass wirklich geläutet wird:

- **Extension:** startet immer im **Simulationsmodus** (Schalter oben). Es wird
  nichts an die Anlage gesendet; du siehst nur, was passieren *würde*, und im
  **Ereignis-Log** die echten Antworten der Anlage (online, Programmliste …).
  Erst nach bewusstem Ausschalten der Simulation wird real geläutet.
- **Gateway:** `python scheduler.py --dry-run` (oder dauerhaft `VOCO_SIMULATION=1`
  in der `.env`) plant und protokolliert, löst aber **nicht** aus.

Verbinden und Status lesen ist ungefährlich – **nur** „Läuten"/„START" löst aus.

## Schnellstart

1. **Extension bauen:** GitHub baut auf Knopfdruck eine installierbare ZIP
   (Tab **Actions** → Workflow „ChurchTools-Extension bauen (ZIP)"), oder lokal
   `cd extension && npm install && npm run deploy`. Details in der Anleitung.
2. **In ChurchTools hochladen:** Admin → Erweiterungen → ZIP installieren.
3. **Gerät + Regeln** im Modul „Glockensteuerung" eintragen (Simulation lassen!).
4. **Gateway** auf einem Dauer-Rechner einrichten und mit `--dry-run` testen.
5. Wenn alles stimmt: Simulation aus → scharf.

→ Alle Schritte im Detail: **[`ANLEITUNG.md`](ANLEITUNG.md)**

## Dokumentation

- [`ANLEITUNG.md`](ANLEITUNG.md) – **komplette Einrichtung** Schritt für Schritt.
- [`docs/VOCO-MQTT-Protokoll.md`](docs/VOCO-MQTT-Protokoll.md) – Steuerprotokoll (belegt).
- [`docs/Konzept.md`](docs/Konzept.md) – Gesamtkonzept & Architektur.
- [`docs/Handbuch-Auswertung.md`](docs/Handbuch-Auswertung.md) – Auswertung der Bedienungsanleitung.
- [`docs/HEW-Rueckfragen.md`](docs/HEW-Rueckfragen.md) – Anfrage an HEW (offizielle Schnittstelle).
- [`docs/Variante-A-Plan.md`](docs/Variante-A-Plan.md) – Rückfall-Variante (Relais an Geräte-Eingänge).
- [`docs/mockup/glockensteuerung-mockup.html`](docs/mockup/glockensteuerung-mockup.html) – Design-Mockup der Oberfläche.

## 🔐 Wichtig

- Geräte-Passwort, ChurchTools-Token & Login-Daten sind **Geheimnisse** – niemals
  ins Repository, in Chats oder Screenshots. Lokal nur in `.env` (ausgeschlossen
  per `.gitignore`).
- Die Steuerung nutzt das **nachgebaute** HEW-Cloud-Protokoll. Für dauerhaften
  Betrieb – besonders bei mehreren Gemeinden – ist eine **offizielle Freigabe von
  HEW** empfehlenswert (siehe `docs/HEW-Rueckfragen.md`).
