# Konzept: Automatische Läuteprogramm-Auswahl über ChurchTools

**Projekt:** Verbindung der Glockenläutesteuerung HEW VOCO-futura ST5 mit ChurchTools
**Ziel:** Das passende Läuteprogramm wird automatisch anhand der Termine im
ChurchTools-Veranstaltungsmodul ausgelöst – die manuelle Programmwahl entfällt.
**Stand:** Konzeptphase (Entwurf), {Datum: 2026-05}

---

## 1. Ausgangslage und Ziel

Aktuell muss für jeden Gottesdienst / jede Veranstaltung das passende
Läuteprogramm an der ST5 von Hand ausgewählt bzw. eingeplant werden. Da die
Termine ohnehin in ChurchTools gepflegt werden, sollen diese als „Quelle der
Wahrheit" dienen:

> ChurchTools-Termin (mit Zeit + Art der Veranstaltung)
> → automatisch das richtige Läuteprogramm zur richtigen Zeit auslösen.

**Nicht-Ziele (vorerst):**
- Ersetzen der Hersteller-Bedienung / der internen Jahresautomatik der ST5
  (diese soll als Rückfall- und Sicherheitsebene erhalten bleiben).
- Steuerung einzelner Glocken in Echtzeit (z. B. Trauerläuten on demand).

---

## 2. Beteiligte Systeme

### 2.1 HEW VOCO-futura ST5 (Läutesteuerung)

Bekannt (Herstellerangaben / Datenblatt):
- Funkschaltuhr (DCF77-Zeitsynchronisation).
- Steuert bis zu **5 Läutekreise** (bzw. 4 Glocken + Schlagwerk).
- Speichert **Läute- und Sonderprogramme**, die über einen internen
  **Jahreskalender** automatisch nach Datum/Wochentag ausgewählt werden.
- Die *futura*-Serie verfügt über ein **LAN-Anschlussmodul** (WLAN optional)
  und eine **VOCO-futura App** zur Fern-Programmierung/-Steuerung.

⚠️ **Kritische, noch offene Frage (in Klärung):**
Es ist **nicht öffentlich dokumentiert**, wie sich ein konkretes Läuteprogramm
**von außen auslösen** lässt. Die App nutzt ein **proprietäres, nicht
offengelegtes Protokoll**.

> **Entscheidung:** Es wird **Variante B (LAN-/WLAN-Anbindung)** verfolgt, und das
> Protokoll wird per **eigener Datenverkehrs-Analyse** (App ↔ ST5) ermittelt.
> Vorgehen Schritt für Schritt in [`Protokoll-Analyse.md`](Protokoll-Analyse.md).
> Offen ist noch, ob die App **lokal** oder **über die HEW-Cloud** steuert
> (Test in der Analyse-Anleitung, Schritt 0).

### 2.2 ChurchTools (Terminquelle)

- Bietet eine dokumentierte **REST-API** (OpenAPI/Swagger), erreichbar unter
  `https://<gemeinde>.church.tools/api`.
- Authentifizierung empfohlen über **Login-ID + Token** (eigener „technischer"
  Benutzer, unabhängig vom persönlichen Account).
- Relevant: das **Veranstaltungsmodul (Events)** – Endpunkt voraussichtlich
  `GET /api/events` mit Start-/Endzeit, Kalender, Kategorie/Art usw.
  (Details in [`ChurchTools-API.md`](ChurchTools-API.md); gegen die
  Swagger-Doku der eigenen Instanz verifizieren.)

### 2.3 Gateway (Brücke vor Ort)

- Vorhandener **Dauer-PC vor Ort mit Internetzugang** (Festlegung des Nutzers).
- Soll als Vermittler dienen: ChurchTools auslesen → Zeitplan bilden →
  zur richtigen Zeit die ST5 auslösen.

---

## 3. Gesamtarchitektur (Soll)

```
   ┌──────────────────────────┐        REST/HTTPS        ┌────────────────────┐
   │       ChurchTools         │ ◄──────────────────────► │   Gateway (Dauer-  │
   │  Veranstaltungsmodul      │   GET /api/events        │   PC vor Ort)      │
   └──────────────────────────┘                          │                    │
                                                          │  1. Termine holen  │
   ┌──────────────────────────┐                          │  2. Mapping         │
   │   Mapping-Tabelle:        │ ◄────────────────────────│     Termin→Programm│
   │   Veranstaltungsart →     │                          │  3. Zeitplan        │
   │   Läuteprogramm/Eingang   │                          │  4. Auslösen        │
   └──────────────────────────┘                          └─────────┬──────────┘
                                                                    │
                                            (Ansteuerung – siehe §4) ▼
                                                          ┌────────────────────┐
                                                          │  VOCO-futura ST5    │
                                                          │  Läuteprogramm X    │
                                                          └────────────────────┘
```

**Ablauf (fachlich):**
1. Gateway ruft regelmäßig (z. B. alle 5–15 min) die kommenden Termine aus
   dem ChurchTools-Veranstaltungsmodul ab.
2. Über eine konfigurierbare **Mapping-Tabelle** wird je Termin das passende
   Läuteprogramm bzw. der passende Steuer-Eingang der ST5 bestimmt
   (z. B. „Veranstaltungsart = Gottesdienst" → Programm 1 = Vorläuten + Einläuten).
3. Daraus wird ein **Zeitplan** mit konkreten Auslösezeitpunkten gebildet
   (inkl. **Vorläuten-Vorlaufzeit** vor Veranstaltungsbeginn).
4. Zum Zeitpunkt löst das Gateway das Programm an der ST5 aus (Mechanismus
   abhängig von der in §4 zu klärenden Schnittstelle).

---

## 4. Schnittstelle zur ST5 – Entscheidungsbaum (kritisch)

Die Umsetzbarkeit steht und fällt mit der Frage, **wie die ST5 ein Programm
von außen entgegennimmt**. Drei mögliche Wege, in Reihenfolge der Robustheit:

### Variante A – Potentialfreie Steuereingänge (bevorzugt)
*Voraussetzung:* Die ST5 besitzt externe Eingänge, über die sich Läuten/Programme
per Kontaktschluss auslösen lassen (bei Läutesteuerungen üblich, z. B. für
Sakristei-Taster, Notläuten, Beerdigung).

- **Gateway → USB-Relaiskarte → ST5-Eingänge.** Jeder Eingang = ein Programm.
- ✅ Robust, herstellerunabhängig, galvanisch getrennt, keine Cloud nötig.
- ⚠️ Verdrahtung durch Elektrofachkraft; Anzahl Eingänge begrenzt die Anzahl
  direkt auslösbarer Programme.

### Variante B – LAN-/WLAN-Modul (proprietäres Protokoll)
*Voraussetzung:* HEW gibt eine dokumentierte/offizielle Schnittstelle frei.

- Gateway spricht die ST5 über das Netzwerk an.
- ⚠️ Aktuell **kein offenes Protokoll** bekannt; Reverse-Engineering der App
  wäre fragil und für eine sicherheitsrelevante Glockenanlage **nicht ratsam**.
- → Nur gangbar **mit aktiver Unterstützung durch HEW**.

### Variante C – Keine externe Auslösung möglich
Falls die ST5 ausschließlich über internen Kalender + App bedienbar ist,
ist eine direkte Live-Auslösung nicht möglich. Mögliche Auswege:
- ST5-Hardware-Erweiterung / Nachrüstmodul mit Steuereingängen bei HEW anfragen.
- ChurchTools-Termine nur als **Planungs-/Abgleichshilfe** nutzen
  (z. B. wöchentlicher Soll/Ist-Report, der manuelle Programmierung erleichtert),
  ohne automatische Auslösung.

> **Nächster Schritt vor jeder Implementierung:** Variante A/B/C anhand
> ST5-Handbuch klären bzw. die Fragen aus [`HEW-Rueckfragen.md`](HEW-Rueckfragen.md)
> an HEW stellen.

---

## 5. Wo läuft die Logik? (später zu entscheiden)

Zwei Optionen – Entscheidung bewusst aufgeschoben (Nutzer: „erst Konzept"):

| | **Variante 1: Lokal auf dem Gateway** | **Variante 2: Supabase-Cloud + lokaler Agent** |
|---|---|---|
| Termin-Abruf | PC ruft ChurchTools direkt ab | Edge Function synchronisiert Termine in DB |
| Zeitplan/Mapping | komplett auf dem PC | in der Cloud, PC holt nur Befehle ab |
| Vorteil | einfach, keine Cloud-Abhängigkeit, läuft auch bei Cloud-Ausfall | Fernkonfiguration, Monitoring, Mehrere Standorte |
| Nachteil | Konfiguration nur lokal | mehr Komplexität, Cloud nötig |
| Empfehlung | **Start hier** (MVP) | optionaler Ausbau später |

> Empfehlung: Mit **Variante 1 (lokal)** starten – minimale Abhängigkeiten,
> kein Single-Point-of-Failure in der Cloud. Supabase (in dieser Umgebung
> verfügbar) optional später für Monitoring/Fernwartung ergänzen.

---

## 6. Mapping Veranstaltung → Läuteprogramm

Da als Quelle das **Veranstaltungsmodul** gewählt wurde, wird je Veranstaltung
ein Programm zugeordnet. Vorschlag für eine konfigurierbare Mapping-Tabelle:

| Feld | Beispiel | Zweck |
|---|---|---|
| Veranstaltungsart / Kategorie | „Gottesdienst", „Andacht", „Trauung" | Hauptkriterium fürs Programm |
| Wochentag/Uhrzeit (optional) | So 10:00 | Feinunterscheidung |
| Läuteprogramm / ST5-Eingang | Programm 1 / Eingang 1 | Was ausgelöst wird |
| Vorlaufzeit Vorläuten | 15 min | Wann ausgelöst wird |
| Aktiv ja/nein | ja | Sicherheits-Schalter pro Regel |

Offen: Welche Veranstaltungsarten existieren in eurer ChurchTools-Instanz und
welches Läuteprogramm gehört jeweils dazu? (→ Abschnitt 9, gemeinsam zu befüllen.)

---

## 7. Sicherheits- und Betriebsüberlegungen

Glockenläuten ist **außenwirksam** (Lärmschutz, Nachtruhe, Nachbarschaft) und
damit sicherheitsrelevant. Leitlinien:

- **Fail-safe:** Im Zweifel **nicht** läuten ist besser als **falsch** läuten.
- **Interne ST5-Automatik als Rückfallebene** beibehalten; die Integration soll
  ergänzen, nicht ersatzlos überschreiben.
- **Zeitfenster/Plausibilität:** keine Auslösung außerhalb erlaubter Zeiten
  (z. B. nachts), Obergrenze für Läutedauer.
- **Umgang mit Änderungen:** verschobene/abgesagte Termine in ChurchTools
  müssen den Zeitplan zuverlässig aktualisieren (inkl. kurzfristiger Absagen).
- **Manueller Vorrang / Not-Aus:** Vor-Ort-Bedienung muss jederzeit Vorrang haben.
- **Logging & Benachrichtigung:** jede Auslösung protokollieren; Fehler
  (z. B. ChurchTools nicht erreichbar) melden.
- **Zeitbasis:** Gateway-Uhr (NTP) und ST5 (DCF77) – Zeitabweichungen beachten.

---

## 8. Offene Fragen / zu klären

1. **ST5-Schnittstelle (blockierend):** Variante A/B/C? → Handbuch / HEW
   (siehe [`HEW-Rueckfragen.md`](HEW-Rueckfragen.md)).
2. **ChurchTools-Zugang:** Gibt es Admin-Rechte, um einen technischen Benutzer
   + API-Token anzulegen? Wie lautet die Instanz-URL?
3. **Veranstaltungsarten:** Welche Arten/Kategorien gibt es, und welches
   Läuteprogramm gehört jeweils dazu?
4. **Gateway-PC:** Betriebssystem, freie USB-Ports (für ggf. Relaiskarte),
   darf darauf ein Hintergrunddienst laufen?
5. **Bestehende ST5-Programme:** Welche Programme (1–n) sind belegt und was tun sie?

---

## 9. Nächste Schritte

1. **ST5-Protokoll ermitteln** (Variante B): Datenverkehr App↔ST5 analysieren
   gemäß [`Protokoll-Analyse.md`](Protokoll-Analyse.md) – inkl. Test lokal/Cloud.
2. ChurchTools-API-Zugang einrichten (technischer Benutzer + Token) und
   `GET /api/events` an der eigenen Instanz testen.
3. Bestehende Läuteprogramme + Veranstaltungsarten erfassen und die
   Mapping-Tabelle (Abschnitt 6) befüllen.
4. Auf dieser Basis: Detailspezifikation + MVP (Variante 1 lokal) planen.

---

*Dieses Dokument ist ein lebender Entwurf und wird mit den Antworten zu
Abschnitt 8/9 fortgeschrieben.*
