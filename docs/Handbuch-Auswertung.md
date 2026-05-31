# Handbuch-Auswertung VOCO-futura ST5

Auswertung der **Kurzanleitung** (Software v1.27, 03/2021) — vollständig gelesen.
Die große Bedienungsanleitung (51 S.) ließ sich in der Auswertungsumgebung
technisch nicht rendern; offene Detailfragen unten sind entsprechend markiert.

> Methodischer Hinweis: Während dieser Auswertung waren die Ausgaben des
> Shell-Tools unzuverlässig/manipuliert. Die hier dokumentierten Fakten stammen
> **ausschließlich aus dem direkt gelesenen PDF-Inhalt** der Kurzanleitung.

---

## 1. Was die ST5 ist (belegt)

- **Eigenständige Digital-Hauptuhr mit Touchscreen.** Alle Läuteprogramme
  (**PGS** = Programmschritte) werden **direkt am Gerät** angelegt/gestartet.
- Ein PGS hat: **Name, PGS-Modus** (Einmalig, Täglich, wöchentlich, 2-wöchentlich,
  Mo-Fr, Mo-Sa, jährlich, …), **Start-Datum, Start-Zeit, PGS-Typ**
  (Läuten / Sperrprogramm / Melodie), **Läutedauer**, **Ausgänge/Melodie**.
- **Sofort-PGS:** ein Programm lässt sich **sofort** starten **oder** auf einen
  Zeitpunkt planen („Starten Um:"). Das ist der manuelle Auslöse-Mechanismus.
- **STOP-Taste** bricht laufende/geplante Programme ab.

## 2. Internet / Netzwerk (belegt, aber begrenzt)

- Das Gerät kann eine **Internetverbindung** haben; im Sperrbildschirm wird
  **„Zeitempfang (Internet oder DCF)"** angezeigt.
- ⚠️ **In der Kurzanleitung wird Internet ausschließlich für den ZEITEMPFANG
  beschrieben** — **nicht** für Fernsteuerung.
- ❗ **Kein Wort über App, Smartphone, WLAN-Steuerung oder Cloud-Portal** in der
  Kurzanleitung. Die dokumentierte Bedienung ist der **Touchscreen am Gerät**.
  → Die frühere „App steuert über Cloud"-Annahme ist damit **nicht** durch die
  Doku gedeckt (bleibt offen für die große Anleitung).

## 3. Anschlüsse — der entscheidende Fund für eine externe Ansteuerung ✅

Aus Kapitel **3.2 Anschlussbelegung** (Kurzanleitung S. 9):

- Klemmen **G1–G5**: dienen für **Glocken, Eingänge ODER Ausgänge**. In der
  „Stromkreisbelegung"-Tabelle gibt es je Stromkreis die Spalten **Eingang** und
  **Ausgang** → **jeder Kreis ist als Eingang oder Ausgang konfigurierbar.**
- **Eingänge sind 230 V AC** (Erkennung über 230 V zwischen N und GX) und
  **NICHT potentialfrei** (R ≈ 220 kΩ). HEW empfiehlt für Kleinspannung/
  Fremdspannung ein **externes Koppelrelais**.
- **P1 / P2**: zwischen **L–P1** bzw. **P1–P2** lassen sich optional **externe
  Schalter (Automatikschalter) zur Gruppensteuerung** anschließen (sonst Brücke).
- **DCF77**-Antenne separat (DCF-/DA/DCF+).

➡️ **Konsequenz:** Es gibt **physische Eingänge**, über die sich von außen etwas
auslösen lässt — per **Koppelrelais** (Gateway-PC → Relaiskarte → 230 V an GX
bzw. P1/P2). Das ist die **robuste „Variante A"**, **unabhängig von App/Cloud/
Protokoll**.

## 4. Offene Detailfragen (für die große Bedienungsanleitung)

1. **Was genau bewirkt ein aktivierter Eingang?** Startet er einen bestimmten
   **PGS/eine Melodie**, oder schaltet er nur einen **einzelnen Läutekreis/eine
   Glocke** direkt? (Entscheidend dafür, ob wir „Programme" oder nur „Glocken"
   fernauslösen können.)
2. **P1/P2 Gruppensteuerung:** Welche Programme/Gruppen werden damit ausgelöst?
3. **Internet-Funktion:** Nur Zeitempfang, oder doch Fern-/App-Anbindung?
   Gibt es WLAN/LAN-Einrichtung, Konto/`hew-voco.de`?
4. Liste der **tatsächlich vorhandenen PGS** in eurer Anlage (Namen).

> Diese Punkte klären wir aus der großen Anleitung (bitte Kapitel „Eingänge/
> Ausgänge", „Einstellungen", „Internet/Netzwerk" als Fotos schicken) **oder**
> direkt bei HEW.

## 5. Bewertung der Wege (aktualisiert)

| Weg | Stand nach Handbuch |
|---|---|
| **A: Eingänge + Koppelrelais** | **Bestätigt machbar** (G1–G5 als Eingang, P1/P2). Robust, kein Cloud/Protokoll nötig. **Empfohlen.** |
| B: LAN/App-Protokoll | Durch Doku **nicht** belegt; lokal kein Port gefunden. Unsicher. |
| C: HEW-Cloud-API | Nur Hypothese (Login-Portal existiert). Bei HEW zu erfragen. |

→ Empfehlung: **Variante A weiterverfolgen**, sobald Detailfrage 1 geklärt ist
(was lösen die Eingänge aus). Parallel HEW fragen (Anfrage liegt bereit).
