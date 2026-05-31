# Lesbaren Mitschnitt erzeugen (Klartext statt verschlüsseltem WLAN)

**Warum:** Die bisherigen Fritz!Box-WLAN-Mitschnitte (`wlan-133…`, `wlan-135…`)
sind zwar lesbar, enthalten aber **keinen einzigen Datenpunkt der Steuerung
`192.168.178.151`** – nur unbeteiligtes Hintergrundrauschen (mDNS, IPv6, ARP,
Broadcasts) anderer Geräte. Die eigentliche TCP-Verbindung Handy↔VOCO auf
Port 25423 wurde nicht erfasst. Wir brauchen einen Mitschnitt, der **genau diese
Verbindung enthält** (vor dem Hochladen mit Wireshark-Filter `tcp.port == 25423`
prüfen!).

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

## Methode B (Alternative): Fritz!Box-Mitschnitt – aber richtig

Falls die App nur im gewohnten Netz funktioniert. Der vorige Versuch hat den
VOCO-Verkehr verfehlt – diesmal sicherstellen, dass er enthalten ist:

1. Fritz!Box-Mitschnitt `http://fritz.box/html/capture.html` starten.
   - **Richtige Schnittstelle wählen:** die, über die das **Handy** läuft
     (WLAN). Hängt die ST5 am LAN-Kabel, ggf. zusätzlich die LAN-Schnittstelle
     mitschneiden.
2. **Parallel** in der App die ST5 ansteuern (verbinden, Status, ggf. ein
   Programm – welches gemerkt). Erst **danach** die Aufnahme stoppen.
3. `.eth` in **Wireshark** öffnen, Filter `tcp.port == 25423`.
   - **Pakete sichtbar?** → Rechtsklick → **Follow → TCP Stream** → Screenshot
     (Hex/Roh-Ansicht) teilen **oder** Datei hochladen.
   - **Keine Pakete?** → der Mitschnitt hat den Verkehr wieder verfehlt →
     Methode A (PC-Hotspot) verwenden, die garantiert den Handy-Verkehr sieht.

> Sollten WLAN-Frames ausnahmsweise doch verschlüsselt sein (protected), in
> Wireshark unter *IEEE 802.11* mit `wpa-pwd = WLAN-PASSWORT:SSID` entschlüsseln
> (Passwort nur lokal eingeben, nicht ins Repo/Chat).

---

## Was wir aus dem lesbaren Mitschnitt brauchen

- Bestätigung **lokal** (App spricht direkt mit `192.168.178.151`, nicht Cloud).
- Den **exakten Bytestrom** der Verbindung auf Port 25423 – insbesondere die
  Nachricht, die beim **Auslösen eines Programms** gesendet wird.
- Dazu: **welches Programm** in der App gedrückt wurde (zum Abgleich).
