# Uhrsteuerung – ChurchTools ⇄ VOCO-futura ST5

Anbindung der Glockenläutesteuerung **HEW VOCO-futura ST5** an **ChurchTools**,
damit das passende Läuteprogramm automatisch anhand der Termine im
ChurchTools-**Veranstaltungsmodul** ausgelöst wird – ohne manuelle Programmwahl.

> **Status:** Konzeptphase. Es wird noch kein Code entwickelt.
> Zunächst werden Architektur und offene Fragen festgehalten.

## Dokumente

- [`docs/Konzept.md`](docs/Konzept.md) – Gesamtkonzept, Architektur, Varianten,
  Sicherheitsüberlegungen und nächste Schritte.
- [`docs/HEW-Rueckfragen.md`](docs/HEW-Rueckfragen.md) – Konkrete Fragen an HEW
  zur externen Ansteuerbarkeit der ST5 (kritischer Klärungspunkt).
- [`docs/ChurchTools-API.md`](docs/ChurchTools-API.md) – Notizen zur
  ChurchTools-REST-API und zum Auslesen des Veranstaltungsmoduls.

## Kurzüberblick

```
ChurchTools (Veranstaltungsmodul)            VOCO-futura ST5 (5 Läutekreise)
        │  REST-API (/api/events)                     ▲
        │                                             │ ??? offene Frage:
        ▼                                             │ wie von außen auslösbar?
 ┌─────────────────────────┐                          │
 │  Gateway (Dauer-PC       │   Zeitplan → Auslösung   │
 │  vor Ort, mit Internet)  │ ────────────────────────►│
 └─────────────────────────┘
```

Der **entscheidende, noch offene Punkt** ist, wie sich die ST5 von außen
ansteuern lässt (potentialfreie Steuereingänge vs. proprietäres LAN/App-Protokoll).
Davon hängt die gesamte Umsetzung ab – siehe Konzept.
