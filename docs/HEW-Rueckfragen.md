# Rückfragen an HEW (Herforder Elektromotoren-Werke) zur VOCO-futura ST5

**Zweck:** Klären, ob und wie sich an der VOCO-futura ST5 ein bestimmtes
Läuteprogramm **von außen / automatisiert auslösen** lässt. Dies ist der
entscheidende Punkt für die geplante ChurchTools-Anbindung.

**Kontakt:** HEW Kirchturmtechnik, https://www.hew-hf.de/kirchturmtechnik/
(Anlagen-/Seriennummer der eigenen ST5 bereithalten.)

**Stand:** Wird **parallel** zur eigenen Datenverkehrs-Analyse
([`Protokoll-Analyse.md`](Protokoll-Analyse.md)) verfolgt. Eine offizielle
HEW-Schnittstellen-Doku wäre die bevorzugte, dauerhaft wartbare Lösung.

---

## Sendebereites Anschreiben (E-Mail / Kontaktformular)

> Platzhalter in `[…]` vor dem Senden ausfüllen.

**Betreff:** Anfrage Netzwerk-Schnittstelle / Protokoll VOCO-futura ST5 – Anbindung an Kalendersystem

> Sehr geehrte Damen und Herren,
>
> wir betreiben in unserer Gemeinde [Name der Kirchengemeinde / Ort] eine
> Läutesteuerung **VOCO-futura ST5** (Anlagen-/Seriennummer: [SN]). Die Anlage
> ist über das mitgelieferte **LAN-Modul** mit unserem Netzwerk verbunden und
> wird mit der **VOCO-futura App** bedient.
>
> Wir möchten die **Auswahl des Läuteprogramms automatisieren**: Unsere Termine
> (Gottesdienste, Veranstaltungen) sind in der Gemeindesoftware **ChurchTools**
> hinterlegt. Ein Rechner vor Ort soll künftig anhand dieser Termine
> **automatisch das passende Läuteprogramm zur richtigen Zeit auslösen**, damit
> die manuelle Programmwahl entfällt.
>
> Dazu bitten wir um Auskunft/Unterstützung:
>
> 1. Gibt es für das **LAN-/WLAN-Modul** der VOCO-futura eine **dokumentierte
>    Schnittstelle/API** (z. B. REST/HTTP, MQTT, Modbus-TCP), über die ein
>    eigenes System ein **bestimmtes Läuteprogramm auslösen** kann?
> 2. Falls ja: Können Sie uns die **Schnittstellen-Dokumentation** bereitstellen
>    (Endpunkte/Befehle, Ports, Authentifizierung)?
> 3. Erfolgt die Steuerung der App **lokal im Netzwerk** oder über einen
>    **HEW-Cloud-Dienst**? Ist eine Anbindung durch Drittsysteme vorgesehen?
> 4. Alternativ: Besitzt die ST5 **potentialfreie Steuereingänge**, über die sich
>    Programme per Kontaktschluss auslösen lassen (inkl. Klemmenplan)? Falls nicht
>    vorhanden – gibt es ein **Nachrüstmodul**?
> 5. Gibt es seitens HEW **Vorgaben oder Bedenken** (Gewährleistung, Sicherheit)
>    zur automatisierten Ansteuerung, die wir beachten sollten?
>
> Über eine kurze Rückmeldung – idealerweise mit Hinweis auf die passende
> technische Dokumentation – freuen wir uns sehr.
>
> Mit freundlichen Grüßen
> [Name], [Funktion], [Kirchengemeinde]
> [Telefon / E-Mail]

---

## Fragen (Detailliste, falls technischer Ansprechpartner)

1. **Externe Steuereingänge:** Besitzt die VOCO-futura ST5 potentialfreie
   Eingänge, über die sich einzelne **Läuteprogramme** (oder einzelne Läutekreise)
   per Kontaktschluss von außen **auslösen** lassen?
   - Wenn ja: Wie viele Eingänge, welche Belegung, wie werden sie konfiguriert?
   - Anschlussplan / Klemmenbelegung verfügbar?

2. **Programmwahl extern:** Lässt sich nicht nur „Läuten Start/Stopp", sondern
   gezielt ein **bestimmtes Programm** über die Eingänge wählen (z. B. binär
   kodiert über mehrere Eingänge)?

3. **LAN-/WLAN-Modul:** Gibt es für die Netzwerkanbindung eine **dokumentierte,
   offizielle Schnittstelle/API** (z. B. REST, MQTT, Modbus-TCP), mit der ein
   Fremdsystem Programme auslösen darf? Falls ja: Dokumentation erhältlich?

4. **App-Protokoll:** Über welches Protokoll kommuniziert die VOCO-futura App
   mit der Steuerung (lokal im LAN oder über einen HEW-Cloud-Dienst)? Ist eine
   Integration durch Dritte vorgesehen/erlaubt?

5. **Nachrüstung:** Falls die vorhandene ST5 keine externen Eingänge hat –
   gibt es ein **Nachrüst-/Erweiterungsmodul**, das solche Eingänge bereitstellt?

6. **Sicherheit/Freigabe:** Gibt es seitens HEW Vorgaben oder Bedenken zur
   automatisierten Ansteuerung (Gewährleistung, Sicherheitsanforderungen,
   zulässige Eingriffstiefe)?

---

## Warum das wichtig ist

- **Eingänge vorhanden (Variante A):** Anbindung über ein lokales Gateway +
  USB-Relaiskarte möglich – robust und herstellerunabhängig.
- **Nur dokumentierte Netzwerk-API (Variante B):** Anbindung über LAN möglich,
  sofern HEW die Schnittstelle freigibt.
- **Keine externe Auslösung (Variante C):** automatische Live-Auslösung nicht
  möglich; dann nur Planungs-/Abgleichshilfe oder Hardware-Nachrüstung.

Siehe Gesamtkonzept: [`Konzept.md`](Konzept.md), Abschnitt 4.
