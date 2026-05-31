# Uhrsteuerung – ChurchTools ⇄ VOCO-futura ST5

Anbindung der Glockenläutesteuerung **HEW VOCO-futura ST5** an **ChurchTools**,
damit das passende Läuteprogramm automatisch anhand der Termine im
ChurchTools-**Veranstaltungsmodul** ausgelöst wird – ohne manuelle Programmwahl.

> **Status:** Handbuch ausgewertet. Gewählter Hauptweg: **Variante A** (Gateway +
> Koppelrelais an die ST5-Eingänge). Plan: [`docs/Variante-A-Plan.md`](docs/Variante-A-Plan.md).

## Bisher gesicherte Fakten (aus Handbuch)

- ST5 hat **5 frei belegbare Stromkreise** (Läuten/Schlag/**Eingang**/Ausgang),
  **5 Eingangskanäle 230 V~, nicht potentialfrei** → externe Auslösung via
  **Koppelrelais** möglich (= Variante A).
- **Offen:** Was genau ein Eingang auslöst (Programm vs. Einzelglocke) — bei HEW
  zu klären, bevor verkabelt wird.
- Fernsteuerung läuft offiziell über das **Web-Portal `www.hew-voco.de`**
  (Benutzerkonto, voller Umfang nur mit kostenpflichtigem Freischaltcode); das
  erklärt, warum lokal kein Steuer-Port auffindbar war. Eine offene API ist
  **nicht** dokumentiert.
- Steuerung im LAN: `192.168.178.151` = `HEW-VOCO.fritz.box`.

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
