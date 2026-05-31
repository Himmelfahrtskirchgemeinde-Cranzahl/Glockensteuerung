# Rückfragen an HEW (Herforder Elektromotoren-Werke) zur VOCO-futura ST5

**Zweck:** Klären, ob und wie sich an der VOCO-futura ST5 ein bestimmtes
Läuteprogramm **von außen / automatisiert auslösen** lässt. Dies ist der
entscheidende Punkt für die geplante ChurchTools-Anbindung.

**Kontakt:** HEW Kirchturmtechnik, https://www.hew-hf.de/kirchturmtechnik/
(Anlagen-/Seriennummer der eigenen ST5 bereithalten.)

---

## Fragen

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
