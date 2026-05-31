# Umsetzungsplan Variante A: Gateway + Koppelrelais an die ST5-Eingänge

Gewählter Hauptweg: Die ChurchTools-Termine lösen über **physische Eingänge** der
ST5 das Läuten aus — **unabhängig von App/Cloud/Protokoll**.

## Belegte Grundlage (Handbuch)

- ST5 hat **5 Schließrelais**; **alle Stromkreise frei belegbar** als
  *Läuteglocke, Schlagglocke, Eingang oder Ausgang* (BA S. 4).
- **5 Eingangskanäle, 230 V~**, Schaltleistung 6 A / 230 V~, **nicht
  potentialfrei** (Techn. Daten, BA S. 38).
- **Eingangserkennung:** 230 V AC zwischen **N** und **GX**. Für Kleinspannung/
  Fremdspannung empfiehlt HEW ein **externes Koppelrelais** (Kurzanleitung 3.2).
- **P1/P2:** zwischen L–P1 bzw. P1–P2 optional **externe Schalter
  (Automatikschalter) zur Gruppensteuerung** (Kurzanleitung 3.2).

## ⚠️ Kritische offene Frage (muss vor Verkabelung geklärt werden)

**Was genau löst ein Eingang aus?** Das Anwender-Handbuch dokumentiert die
Funktion der Eingänge **nicht** (liegt im *Service Mode*). Möglich ist:
- (a) Eingang startet einen **bestimmten Programmschritt/eine Melodie**, oder
- (b) Eingang schaltet nur **einen einzelnen Läutekreis/eine Glocke** direkt.

Davon hängt ab, ob wir **fertige Läuteprogramme** auslösen können (gewünscht)
oder nur einzelne Glocken. **→ Bei HEW / per Service-Mode klären** (in
[`HEW-Rueckfragen.md`](HEW-Rueckfragen.md) ergänzt).

> Hinweis: Da nur 5 Kanäle existieren und diese auch zum **Läuten** gebraucht
> werden, sind nur **wenige** als Eingang nutzbar. Ggf. genügt das (z. B. 1–2
> Eingänge: „Gottesdienst-Geläut", „Sonderläuten"). Genaue Aufteilung mit dem
> Glockensachverständigen/HEW abstimmen.

## Architektur

```
ChurchTools (Events) ──REST──> Gateway-PC (Dauer-PC, vor Ort)
                                   │  bestimmt: welcher Eingang, wann
                                   ▼
                          USB-Relaiskarte (potentialfreie Kontakte)
                                   │  schaltet 230 V (L) auf GX / P-Kontakt
                                   ▼
                          Koppelrelais ──230 V AC──> ST5-Eingang (N–GX)
                                                         │
                                                         ▼
                                                  ST5 löst Läuteprogramm
```

**Warum Koppelrelais:** Die ST5-Eingänge erwarten **230 V** und sind **nicht
potentialfrei**. Die USB-Relaiskarte liefert potentialfreie Kontakte; das
Koppelrelais legt sauber/galvanisch getrennt 230 V auf den ST5-Eingang.
**Installation nur durch Elektrofachkraft (VDE).**

## Hardware (Vorschlag)

- **Gateway:** vorhandener Dauer-PC (hat Internet). Dienst/Skript läuft dort.
- **USB-Relaiskarte** (z. B. 2–4 Kanäle, potentialfreie Wechsler).
- **Koppelrelais** 230 V (Hutschiene), Anzahl = Anzahl genutzter Eingänge.
- Verdrahtung L/N gemäß ST5-Anschlussplan, **Absicherung 10 A** je L-Zuleitung.

## Software (geplant, noch nicht implementiert)

1. **ChurchTools-Reader:** holt kommende Veranstaltungen (Veranstaltungsmodul),
   Auth per Login-Token (`.env`).
2. **Mapping** Veranstaltungsart → Eingang/Programm + **Vorlaufzeit** (Vorläuten).
3. **Scheduler:** plant Auslösezeitpunkte; löst Absagen/Verschiebungen nach.
4. **Relais-Treiber:** aktiviert zur Zeit X den passenden Relaiskanal für die
   konfigurierte **Impulsdauer** (ST5: „Eingang/Impulszeit" je Stromkreis).
5. **Sicherheit:** Zeitfenster-Plausibilität (kein Nachtläuten), Logging jeder
   Auslösung, Fail-safe (im Zweifel nicht auslösen), manueller Vorrang vor Ort.

## Vorteile / Grenzen

+ Robust, herstellerunabhängig, kein Cloud-/Freischaltcode nötig, updatefest.
+ ST5-interne Automatik bleibt als Rückfallebene erhalten.
− Erfordert Elektroinstallation; Anzahl Eingänge begrenzt; Eingangs-Funktion
  muss erst geklärt werden (s. o.).

## Nächste Schritte

1. **HEW/Service:** Was lösen Eingänge aus (Programm vs. Einzelglocke)? Wie viele
   Kanäle können wir bei eurer Belegung als Eingang frei machen?
2. Gewünschte **Läute-Anlässe** definieren (welche ChurchTools-Veranstaltungsart →
   welches Geläut) und auf Eingänge abbilden.
3. Hardware beschaffen; Elektrofachkraft für die Verdrahtung einplanen.
4. Erst dann Software-MVP (lokal auf dem Gateway) bauen.

---

### Alternative bleibt offen
Das **offizielle Portal `www.hew-voco.de`** bietet Fernsteuerung per Browser
(Freischaltcode). Falls HEW dazu eine **API** bestätigt, wäre das ein
verkabelungsfreier Weg — parallel bei HEW miterfragen
([`HEW-Cloud-API.md`](HEW-Cloud-API.md)).
