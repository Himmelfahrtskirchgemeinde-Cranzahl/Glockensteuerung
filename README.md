# Uhrsteuerung – ChurchTools ⇄ VOCO-futura ST5

Anbindung der Glockenläutesteuerung **HEW VOCO-futura ST5** an **ChurchTools**,
damit das passende Läuteprogramm automatisch anhand der Termine im
ChurchTools-**Veranstaltungsmodul** ausgelöst wird – ohne manuelle Programmwahl.

> **Status:** Klärungsphase. Die Hauptfrage ist weiterhin, **wie sich die ST5 von
> außen ansteuern lässt** (lokal im LAN vs. über die HEW-Cloud `app.hew-voco.de`).
> Aktueller Schritt: **Auswertung der Bedienungsanleitung**.

## Bisher gesicherte Fakten

- Steuerung im LAN: `192.168.178.151` = `HEW-VOCO.fritz.box`.
- **Kein** lokal ansteuerbarer Port gefunden; Portscans sind wegen Rate-Limiting
  unbrauchbar (schwankende Ergebnisse).
- `app.hew-voco.de` ist ein **Login-Webportal** → **Verdacht** auf Cloud-Steuerung
  (nicht bewiesen).

## Dokumente

- [`docs/Konzept.md`](docs/Konzept.md) – Gesamtkonzept, Architektur, Varianten.
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
