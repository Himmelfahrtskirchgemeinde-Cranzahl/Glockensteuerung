# Uhrsteuerung – ChurchTools ⇄ VOCO-futura ST5

Anbindung der Glockenläutesteuerung **HEW VOCO-futura ST5** an **ChurchTools**,
damit das passende Läuteprogramm automatisch anhand der Termine im
ChurchTools-**Veranstaltungsmodul** ausgelöst wird – ohne manuelle Programmwahl.

> **Status: Durchbruch.** Die Steuerung erfolgt über **MQTT (WebSocket) am
> HEW-Broker `hew-voco.de:8084`** — belegt aus dem Web-App-Quelltext. Damit ist
> ein **verkabelungsfreier** Weg möglich (kein Relais nötig).
> → Protokoll: [`docs/VOCO-MQTT-Protokoll.md`](docs/VOCO-MQTT-Protokoll.md),
> Client: [`src/voco_mqtt.py`](src/voco_mqtt.py).

## Bisher gesicherte Fakten

- **MQTT-Steuerung (empfohlener Weg):** Programm auslösen =
  `START:<PGS-Name>:INSTANT` an Topic `hew/voco/<Serial><GerätePW>/playpgsD`
  (Broker `hew-voco.de:8084`, WSS, Login `hewWeb`/`vocoWeb`).
- 🔐 Seriennummer + **Geräte-Passwort** = Zugang zum Läuten → **geheim** halten,
  nur in `.env` (siehe [`.env.example`](.env.example)), nie committen.
- Läuft über die **HEW-Cloud** (Broker), also internetabhängig; ggf.
  Freischaltcode-Relevanz beim Test prüfen.
- **Alternative (Rückfall):** Variante A (Eingänge + Koppelrelais),
  [`docs/Variante-A-Plan.md`](docs/Variante-A-Plan.md) — nur falls der MQTT-Weg
  ausfällt.
- Gerät im LAN: `192.168.178.151` = `HEW-VOCO.fritz.box`, Serie ST5, FW 1.27.

## Komponenten (Umsetzung)

```
   ┌────────────────────────────┐        ┌──────────────────────────┐
   │  ChurchTools-Extension     │        │  Gateway-Dienst (Python) │
   │  (Browser-Modul)           │        │  auf dem Dauer-PC        │
   │  • Status + manuell läuten │        │  • liest CT-Termine      │
   │  • Regeln: Termin→PGS      │──KV──▶ │  • + Regeln (aus CT)     │
   └──────────┬─────────────────┘ Config │  • löst automatisch aus  │
              │ MQTT/WSS                  └───────────┬──────────────┘
              ▼                                       │ MQTT/WSS
        ┌───────────────────────  hew-voco.de:8084 ───▼───────────┐
        │              HEW-Broker  →  VOCO-futura ST5              │
        └──────────────────────────────────────────────────────────┘
```

- **[`extension/`](extension/)** – ChurchTools Custom-Module (TypeScript/Vite):
  Bedien-Panel + Konfiguration der Automatik-Regeln. Bauen: `npm run deploy`.
- **[`gateway/`](gateway/)** – Python-Dienst: löst zur Termin-Zeit automatisch
  aus (`python scheduler.py`). Liest Gerät + Regeln aus ChurchTools.
- Beide sprechen den HEW-Broker per MQTT (Protokoll: `docs/VOCO-MQTT-Protokoll.md`).

## Dokumente

- [`docs/Konzept.md`](docs/Konzept.md) – Gesamtkonzept, Architektur, Varianten.
- [`docs/VOCO-MQTT-Protokoll.md`](docs/VOCO-MQTT-Protokoll.md) – **Steuerprotokoll** (belegt).
- [`docs/Handbuch-Auswertung.md`](docs/Handbuch-Auswertung.md) – **Aktueller Schritt:**
  was aus der Bedienungsanleitung zu klären ist (PDF bitte ins Repo laden).
- [`docs/HEW-Cloud-API.md`](docs/HEW-Cloud-API.md) – Hypothese Cloud-Portal/-API (zu prüfen).
- [`docs/HEW-Rueckfragen.md`](docs/HEW-Rueckfragen.md) – sendebereite Anfrage an HEW.
- [`docs/ChurchTools-API.md`](docs/ChurchTools-API.md) – Notizen zur ChurchTools-REST-API.
- [`docs/Analyse-Befunde.md`](docs/Analyse-Befunde.md) – Protokoll der Netzanalyse (Fakten).
- [`docs/Leads.md`](docs/Leads.md) – externe Hinweise (Portal, Handbuch, Foren).
- [`docs/Mitschnitt-Klartext.md`](docs/Mitschnitt-Klartext.md) /
  [`docs/Protokoll-Analyse.md`](docs/Protokoll-Analyse.md) – LAN-Verkehrsanalyse (Fallback).

## Wichtig zur Arbeitsweise

Diese Assistenz läuft in der **Cloud** und hat **keinen Zugriff** auf das lokale
Kirchennetz oder passwortgeschützte Hersteller-Seiten (403). Messungen vor Ort
(Scans, Mitschnitte) und Datei-Uploads (Handbuch-PDF, Mitschnitte) erfolgen daher
durch den Nutzer; Auswertung, Code und ChurchTools-Anbindung übernimmt die Assistenz.
