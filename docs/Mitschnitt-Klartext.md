# Lesbaren Mitschnitt erzeugen (Klartext statt verschlüsseltem WLAN)

**Warum:** Die bisherigen Fritz!Box-WLAN-Mitschnitte (`wlan-133…`, `wlan-135…`)
enthalten nur **WPA2-verschlüsselte 802.11-Frames** (alle Daten-Frames protected,
kein EAPOL-Handshake). Sie sind inhaltlich **nicht lesbar** und auch nachträglich
**nicht entschlüsselbar**. Wir brauchen einen Mitschnitt mit **Klartext-IP**.

Ziel ist immer: die TCP-Verbindung **Handy/App → `192.168.178.151:25423`** im Klartext.

---

## Methode A (empfohlen): PC als WLAN-Hotspot + Wireshark

Der Windows-PC wird zum WLAN-Access-Point. Da er die WLAN-Verschlüsselung selbst
terminiert, sieht Wireshark den **entschlüsselten** Verkehr.

1. **Wireshark** installieren (falls noch nicht): https://www.wireshark.org/download.html
   (Npcap mitinstallieren/erlauben).
2. Windows: **Einstellungen → Netzwerk und Internet → Mobiler Hotspot → Ein.**
   (Freigabe über die vorhandene Verbindung des PCs.)
3. **Handy** mit dem PC-Hotspot verbinden (vom Kirchen-WLAN trennen).
4. **App-Test:** App öffnen – findet/verbindet sie die ST5 noch? (Wichtig, weil
   das Handy nun in einem anderen Subnetz ist.)
   - **Ja →** weiter mit Schritt 5.
   - **Nein →** Methode B verwenden (App braucht offenbar das gleiche Netz).
5. In **Wireshark** den Adapter **„LAN-Verbindung* (Mobiler Hotspot)"** als Aufnahme
   starten. Filter: `tcp.port == 25423`
6. In der App die Aktionen ausführen: verbinden, Status abrufen, und – **nur wenn
   unkritisch** – **ein bestimmtes Programm auslösen** (merken: *welches*!).
7. Aufnahme stoppen → **Datei → Speichern unter** → `.pcapng`.
8. Datei ins Repo hochladen (GitHub → „Add file" → „Upload files").

---

## Methode B (Alternative): WLAN-Mitschnitt MIT Handshake + Wireshark entschlüsseln

Falls die App nur im gewohnten Netz funktioniert:

1. Fritz!Box-Mitschnitt starten (`http://fritz.box/html/capture.html`, WLAN-Interface).
2. **Während** der Aufnahme: Handy-**WLAN aus- und wieder einschalten**
   → so wird der **4-Wege-Handshake** mit aufgezeichnet (Pflicht zum Entschlüsseln).
3. App öffnen, Aktionen ausführen (s. o., welches Programm gemerkt).
4. Aufnahme stoppen → `.eth`.
5. In **Wireshark** entschlüsseln:
   **Bearbeiten → Einstellungen → Protocols → IEEE 802.11**
   → „Enable decryption" + Schlüssel **`wpa-pwd`** = `WLAN-PASSWORT:SSID`.
6. Filter `tcp.port == 25423` → Rechtsklick → **Follow → TCP Stream**
   → den Inhalt als **Screenshot** teilen (Hex/Roh-Ansicht).

> WLAN-Passwort **nicht** ins Repo/Chat schreiben – die Entschlüsselung passiert
> lokal in Wireshark.

---

## Was wir aus dem lesbaren Mitschnitt brauchen

- Bestätigung **lokal** (App spricht direkt mit `192.168.178.151`, nicht Cloud).
- Den **exakten Bytestrom** der Verbindung auf Port 25423 – insbesondere die
  Nachricht, die beim **Auslösen eines Programms** gesendet wird.
- Dazu: **welches Programm** in der App gedrückt wurde (zum Abgleich).
