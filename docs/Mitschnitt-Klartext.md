# Brauchbaren Mitschnitt des App-Verkehrs erzeugen

**Warum:** Die bisherigen Fritz!Box-WLAN-Mitschnitte (`wlan-133…`, `wlan-135…`)
sind zwar lesbar, enthalten aber **keinen einzigen Datenpunkt der Steuerung
`192.168.178.151`** – nur unbeteiligtes Hintergrundrauschen (mDNS, IPv6, ARP,
Broadcasts) anderer Geräte. Auch **Portscans sind unbrauchbar** (das Gerät
drosselt sie, Ergebnisse schwanken bei jedem Lauf). Wir brauchen daher einen
Mitschnitt, der die **echte Verbindung Handy↔VOCO** enthält.

> **Filter immer auf die Geräte-IP, nicht auf einen Port:** `ip.addr == 192.168.178.151`
> – den richtigen Port kennen wir noch nicht; er ergibt sich aus dem Mitschnitt.

Ziel ist immer: die Verbindung **Handy/App ↔ `192.168.178.151`** im Klartext –
**oder** der Nachweis, dass die App stattdessen ins Internet (HEW-Cloud
`app.hew-voco.de`) telefoniert.

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
   starten. Filter: `ip.addr == 192.168.178.151`
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
3. `.eth` in **Wireshark** öffnen, Filter `ip.addr == 192.168.178.151`.
   - **Pakete sichtbar?** → Rechtsklick → **Follow → TCP Stream** → Screenshot
     (Hex/Roh-Ansicht) teilen **oder** Datei hochladen.
   - **Keine Pakete?** → der Mitschnitt hat den Verkehr wieder verfehlt →
     Methode A (PC-Hotspot) verwenden, die garantiert den Handy-Verkehr sieht.

> Sollten WLAN-Frames ausnahmsweise doch verschlüsselt sein (protected), in
> Wireshark unter *IEEE 802.11* mit `wpa-pwd = WLAN-PASSWORT:SSID` entschlüsseln
> (Passwort nur lokal eingeben, nicht ins Repo/Chat).

---

## Was wir aus dem Mitschnitt brauchen

- **Lokal oder Cloud?** Spricht die App direkt mit `192.168.178.151` – oder mit
  einer Internet-Adresse (HEW-Cloud `app.hew-voco.de`)? Das ist die zentrale Frage.
- Den **echten Port** und den **exakten Bytestrom** der relevanten Verbindung –
  insbesondere die Nachricht, die beim **Auslösen eines Programms** gesendet wird.
- Dazu: **welches Programm** in der App gedrückt wurde (zum Abgleich).

> **Wichtiger Hinweis (neu):** `app.hew-voco.de` ist ein **Web-Portal mit Login**
> (HEW-Cloud). Es ist daher gut möglich, dass die App **nicht lokal**, sondern
> über diese Cloud steuert. Dann zeigt der Mitschnitt Verkehr zu einer
> öffentlichen IP statt zu `192.168.178.151` – und eine saubere Anbindung liefe
> über die Cloud (API von HEW nötig), nicht über das LAN.
