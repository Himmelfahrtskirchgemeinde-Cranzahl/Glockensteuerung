# ChurchTools-API: was dieses Projekt benutzt

Keine Arbeitsnotizen mehr, sondern der Stand, der im Betrieb läuft. Alles hier
ist an einer echten Instanz erprobt – der Gateway (`gateway/churchtools.py`)
und die Extension (`extension/src/`) sprechen genau so mit ChurchTools.

Zum Nachschlagen der vollständigen API: `https://<gemeinde>.church.tools/api`

---

## Anmeldung

Der Gateway meldet sich mit dem **Login-Token** eines technischen Benutzers an:

```
GET /api/whoami?login_token=<TOKEN>
```

Das setzt ein **Sitzungs-Cookie**; alle weiteren Aufrufe laufen darüber.

> **Wichtig:** Dieses Cookie **läuft ab**. Danach beantwortet ChurchTools jede
> Anfrage mit `401`. Genau daran ist der Dienst früher gestorben – sichtbar als
> „keine Verbindung" in der Extension und „0 Automationen geplant" im Fenster.
> Der Token wird deshalb behalten und die Sitzung bei `401` **einmal** neu
> aufgebaut; die Anfrage läuft danach weiter, als wäre nichts gewesen.

Der Benutzer braucht Leserechte auf die betreffenden Kalender und auf das
Custom-Module. Der Token gehört in die `.env`, nie ins Repository.

Die Extension braucht das nicht: Sie läuft **in** ChurchTools und benutzt die
Sitzung des angemeldeten Benutzers (`@churchtools/churchtools-client`).

## Antwortform

Nutzdaten stecken in `{"data": …}`. Beide Seiten packen das aus; bei `204` ohne
Inhalt kommt nichts zurück.

## Termine

| Zweck | Endpunkt |
|---|---|
| Kalender auflisten | `GET /api/calendars` |
| Termine mehrerer Kalender | `GET /api/calendars/appointments?calendar_ids[0]=…&from=JJJJ-MM-TT&to=JJJJ-MM-TT` |
| Termine eines Kalenders | `GET /api/calendars/{id}/appointments?from=…&to=…` (Rückfallweg) |

Benutzt werden **Kalender-Termine** (Appointments), nicht das
Veranstaltungsmodul (Events). Grund: Geläutet wird zu dem, was im Kalender
steht – eine verknüpfte Veranstaltung gibt es oft gar nicht.

### Serientermine: `calculated` statt `base`

Je Vorkommen liefert die API `{"appointment": {"base": …, "calculated": …}}`.

- `base.startDate` ist der Beginn der **Serie** – bei einem wöchentlichen
  Gottesdienst liegt der oft Jahre zurück.
- `calculated.startDate` ist der Beginn **dieses** Vorkommens.

Wer `base` nimmt, dessen Serientermine fallen aus dem Zeitfenster und lösen
**nie** aus. Ältere oder abweichende Antworten sind flach oder haben `base`
direkt; alle drei Formen werden abgedeckt (`_norm_appointment` im Gateway,
dieselbe Logik in der Extension).

### Titel, nicht Veranstaltungsart

Die Regeln vergleichen den **Termin-Titel**, und zwar exakt („Gottesdienst"
trifft also nicht auch „Festgottesdienst"). Die Veranstaltungsart hängt an einer
verknüpften Veranstaltung und ist in der Praxis nicht gepflegt – Regeln darauf
griffen nie. Extension und Gateway müssen hier **gleich** entscheiden, sonst
zeigt die Vorschau etwas anderes an, als später läutet.

## Custom Modules: der Speicher der Extension

Gerät, Regeln, Lebenszeichen und Ereignisse liegen im Custom-Module
`glockensteuerung`:

```
GET  /api/custommodules
GET  /api/custommodules/{modulId}/customdatacategories
GET  /api/custommodules/{modulId}/customdatacategories/{katId}/customdatavalues
POST /api/custommodules/{modulId}/customdatacategories/{katId}/customdatavalues
PUT  /api/custommodules/{modulId}/customdatacategories/{katId}/customdatavalues/{wertId}
```

**Das Feld `value` ist ein JSON-STRING**, kein Objekt:

```json
{"value": "{\"key\":\"rules\",\"data\":[…]}"}
```

So schreibt es die Extension (`utils/kv-store.ts`), und so muss der Gateway es
auch schreiben (`gateway/kv.py`) – sonst lesen die beiden aneinander vorbei.

### Ein Eintrag fasst 10 000 Zeichen

Mehr nimmt ChurchTools nicht an:

```
400 – Eingabe muss ein Text sein, der zwischen 0 und 10000 Zeichen enthält.
```

Gezählt wird die ganze Zeichenkette samt `{"key":…,"data":…}`. Abgeschnitten
wird **nichts** – der Schreibversuch scheitert schlicht. Für eine wachsende
Liste heißt das: Sie wird ab einem bestimmten Tag gar nicht mehr gespeichert.
Genau so ist es dem Ereignis-Log ergangen, das als ein Eintrag mit 300 Zeilen
angelegt war (rund 35 000 Zeichen).

Deshalb liegt das Log jetzt in **Wochenblöcken**: ein Eintrag je Kalenderwoche
(`log-2026-W38`), bei viel Betrieb mehrere (`log-2026-W38-2`). Gelesen wird
trotzdem in einer einzigen Abfrage – die API gibt alle Einträge einer
Kategorie zusammen heraus. Alte Wochen fallen als Ganzes weg, statt im Bestand
zu schneiden.

| Schlüssel | Kategorie | Inhalt |
|---|---|---|
| `log-JJJJ-Wnn` | `ereignislog` | Ereignisse dieser Kalenderwoche, neueste zuerst |
| `log-JJJJ-Wnn-2` … | `ereignislog` | Fortsetzung, wenn eine Woche nicht in einen Eintrag passt |
| `log` | `ereignislog` | der frühere Sammel-Eintrag; wird beim ersten Schreiben aufgeteilt und entfernt |

### Kategorien sind Rechte-Schalter

Jedes Untermenü der Extension ist eine eigene Kategorie. Das ist keine
Ordnungsfrage, sondern die Rechtevergabe: Ein Admin vergibt die Rechte je
Kategorie.

| Kategorie (`shorty`) | Inhalt | Wer darf lesen |
|---|---|---|
| `steuerung` | Gerät, Lebenszeichen, Gateway-Ereignisse, Update-Prüfung | jeder, der das Modul bedienen darf |
| `ereignislog` | Ereignis-Log | wie vergeben |
| `regeln` | Automatik-Regeln | wie vergeben |
| `email` | Postausgang (**Zugangsdaten**) | nur Verwalter |

Die Rechte stehen in `GET /api/permissions/global` unter dem Modul-Key, als
Listen von Kategorie-IDs (`view custom data`, `edit custom data`,
`create custom data`). Die Oberfläche blendet danach aus – **erzwungen werden
sie serverseitig**.

## Was im Betrieb wichtig wurde

- **`401` heißt „Sitzung abgelaufen", nicht „Token falsch".** Einmal neu
  anmelden, dann weiter.
- **Ein Aussetzer ist kein leeres Ergebnis.** Schlägt der Terminabruf
  vollständig fehl, wird ein Fehler geworfen statt einer leeren Liste – sonst
  löscht ein zweiminütiger Ausfall den Auslöseplan.
- **Eine halb gelesene Antwort ist keine Konfiguration.** Fehlt das Gerät, wird
  die Antwort verworfen und der bisherige Stand behalten.
- **Keine Leseberechtigung auf eine Kategorie ist kein Fehler**, sondern ein
  Rechte-Zustand: Die Kategorie wird übersprungen.

## Quellen

- API-Doku der eigenen Instanz: `https://<gemeinde>.church.tools/api`
- ChurchTools Academy: <https://churchtools.academy/de/help/system-settings/api-de/api-documentation/>
- extension-boilerplate: <https://github.com/churchtools/extension-boilerplate>
