# Notizen: ChurchTools-REST-API (Veranstaltungsmodul)

Arbeitsnotizen zum Auslesen der Termine aus dem **Veranstaltungsmodul (Events)**.
Alle Endpunkte/Felder gegen die **Swagger-Doku der eigenen Instanz** verifizieren:
`https://<gemeinde>.church.tools/api`

---

## Authentifizierung

- Empfohlen: eigener **technischer Benutzer** mit **Login-Token**
  (unabhängig vom persönlichen Account, jederzeit widerrufbar).
- Üblicher Ablauf (zu verifizieren):
  - Login per `POST /api/login` (Benutzer/Passwort) → Session-Cookie, **oder**
  - Login-Token des Benutzers verwenden (z. B. `Authorization: Login <TOKEN>`).
- Token niemals ins Repository committen → später in einer
  `.env`/Konfiguration außerhalb der Versionsverwaltung ablegen.

## Relevante Endpunkte (voraussichtlich)

| Zweck | Endpunkt (zu verifizieren) |
|---|---|
| Kommende Veranstaltungen | `GET /api/events?from=<Datum>&to=<Datum>` |
| Einzelne Veranstaltung | `GET /api/events/{id}` |
| Kalender/Kategorien | `GET /api/calendars`, ggf. Kategorien-/Art-Endpunkt |
| Verbundener Termin/Appointment | `GET /api/calendars/{id}/appointments` |

Wichtige Felder je Event (Auswahl, zu prüfen): `id`, `name`, `startDate`,
`endDate`, `calendar`, **Kategorie/Veranstaltungsart**, `repeatId` (Serien).

## Für die Anbindung benötigte Informationen

Aus jedem relevanten Event ziehen wir:
- **Startzeit** (→ minus Vorlaufzeit = Auslösezeitpunkt fürs Vorläuten),
- **Veranstaltungsart/Kategorie** (→ Mapping auf Läuteprogramm),
- **Status** (stattfindend / abgesagt / verschoben).

## Offene Punkte

1. Instanz-URL und API-Zugang (technischer Benutzer + Token) einrichten.
2. Genaue Endpunkt-/Feldnamen an der eigenen Swagger-Doku verifizieren
   (API-Versionen v1/v2 unterscheiden sich).
3. Wie werden **Serientermine** und **kurzfristige Absagen** über die API
   abgebildet? (Wichtig für korrekte Zeitplan-Aktualisierung.)
4. Welche **Veranstaltungsarten** existieren und wie heißen sie exakt?

## Hilfreiche Quellen

- API-Doku (Academy): https://churchtools.academy/de/help/system-settings/api-de/api-documentation/
- Community-PHP-Wrapper (Referenz für Endpunkte):
  - https://github.com/5pm-HDH/churchtools-api
  - https://github.com/vineyardkoeln/churchtools-api
- API-Demo: https://github.com/churchtools/ctapidemo
