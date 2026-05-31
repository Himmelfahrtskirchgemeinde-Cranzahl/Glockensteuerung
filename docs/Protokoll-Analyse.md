# Protokoll-Analyse: VOCO-futura App ↔ ST5 (Variante B / LAN)

**Ziel:** Das undokumentierte Protokoll ermitteln, mit dem die VOCO-futura App
die ST5 steuert, damit das Gateway später dieselben Befehle senden kann
(„welches Byte/Kommando löst Programm X aus?").

> **Rechtlicher Rahmen:** Es handelt sich um die **eigene Anlage** der Gemeinde.
> Das Analysieren des Datenverkehrs zwischen *eigenen* Geräten zum Zweck der
> **Interoperabilität** ist zulässig. Bitte nur im eigenen Netz und an der
> eigenen ST5 durchführen.

---

## Schritt 0 – Lokal oder Cloud? (2-Minuten-Test)

Entscheidet, ob eine lokale Anbindung überhaupt möglich ist.

1. Handy mit der App ins **gleiche WLAN** wie die ST5 bringen.
2. **Internet trennen**, WLAN aber anlassen:
   - am Router das **WAN-/DSL-Kabel ziehen** (oder Internetzugang deaktivieren),
   - das interne WLAN/LAN bleibt aktiv.
3. App öffnen und die ST5 ansteuern (Status abrufen / Testfunktion).

**Auswertung:**
- App funktioniert weiter → **lokale Steuerung** ✅ (Anbindung gut machbar).
- App meldet „keine Verbindung" o. Ä. → **Cloud-Steuerung** ⚠️
  (Abhängigkeit von HEW-Servern; lokale Anbindung evtl. nicht möglich →
  dann zusätzlich HEW-Doku/-Freigabe nötig).

Gegenprobe: Handy in **Flugmodus + nur WLAN an** (kein Mobilfunk) – falls die
App dann noch geht, läuft sie definitiv lokal.

> Ergebnis hier eintragen: **[ ] lokal  [ ] Cloud  — Datum/Notiz:** ____________

---

## Schritt 1 – ST5 im Netzwerk finden

Auf dem Gateway-PC (oder einem Laptop im selben Netz):

```bash
# Eigenes Subnetz ermitteln (z. B. 192.168.178.0/24)
ip a            # Linux/macOS
ipconfig        # Windows

# Geräte im Netz suchen (Ping-Sweep)
nmap -sn 192.168.178.0/24

# Offene Ports/Dienste der ST5 (IP aus dem Sweep einsetzen)
nmap -p- -sV 192.168.178.50

# Discovery-Protokolle beobachten (oft mDNS/SSDP)
avahi-browse -a            # Linux (mDNS)
dns-sd -B _services._dns-sd._udp   # macOS (mDNS)
```

Notieren: **IP**, **MAC** (Hersteller-Kennung der ersten 3 Bytes/OUI),
**offene Ports** (z. B. 80/443 = HTTP(S), 1883 = MQTT, oder ein proprietärer Port).

> ST5: IP = __________  MAC/OUI = __________  offene Ports = __________

---

## Schritt 2 – Datenverkehr mitschneiden

In geswitchten Netzen sieht man fremden Verkehr nicht automatisch. Eine der
folgenden Methoden wählen (von einfach zu aufwändig):

### Methode A – Gateway-PC als WLAN-Hotspot (empfohlen, einfach)
Der PC spannt ein WLAN auf, das Handy verbindet sich darüber, der PC
„sieht" damit den gesamten App-Verkehr.
- Handy verbindet sich mit dem PC-Hotspot, die ST5 muss vom PC aus erreichbar sein.
- Mitschnitt auf der Hotspot-Schnittstelle des PCs (siehe unten).

### Methode B – Managed Switch mit Port-Mirroring
Falls ein verwaltbarer Switch vorhanden ist: Port der ST5 auf einen Monitor-Port
spiegeln und dort mit dem PC mitschneiden. Saubere, nicht-invasive Methode.

### Methode C – MITM im eigenen LAN (ARP, falls A/B nicht gehen)
Mit `bettercap`/`ettercap` den Verkehr zwischen Handy und ST5 über den PC leiten.
Invasiver – nur im eigenen Netz, danach sauber beenden.

### Mitschnitt aufnehmen
```bash
# Schnittstelle herausfinden, dann mitschneiden (Linux/macOS)
sudo tshark -i wlan0 -w voco_aktion.pcapng
# oder grafisch: Wireshark öffnen → Interface wählen → aufnehmen
```
Auf Windows: **Wireshark** installieren und das passende Interface wählen.

### Wenn der Verkehr verschlüsselt ist (HTTPS/TLS)
- **mitmproxy** als Proxy einsetzen, dessen **CA-Zertifikat auf dem Handy** (eigenes
  Gerät) installieren → entschlüsselter Mitschnitt.
- Falls **Certificate-Pinning** aktiv ist (App verweigert Proxy): schwieriger,
  ggf. APK-Analyse / Frida nötig. → Dann erst hier weitermelden, bevor du Zeit investierst.

---

## Schritt 3 – Gezielt einzelne Aktionen aufnehmen (wichtig!)

Damit wir die Befehle eindeutig zuordnen können: **jede Aktion einzeln** ausführen
und als **separate, klar benannte** Datei speichern. Zwischen den Aktionen kurz
warten, damit die Aufnahmen getrennt sind.

Empfohlene Aufnahmen (Dateinamen-Vorschlag):

| Datei | Aktion in der App |
|---|---|
| `01_app_verbindet.pcapng` | App starten/koppeln, bis Verbindung steht (Handshake/Discovery) |
| `02_status.pcapng` | Status/Übersicht abrufen |
| `03_programm_1.pcapng` | **Programm 1** auslösen |
| `04_programm_2.pcapng` | **Programm 2** auslösen |
| `05_programm_3.pcapng` | **Programm 3** auslösen |
| `06_laeuten_start.pcapng` | Läuten starten (einzelne Glocke, falls möglich) |
| `07_laeuten_stop.pcapng` | Läuten stoppen |

> Durch Vergleich von `03/04/05` finden wir, **wo im Befehl die Programmnummer
> steht** (und ob es Längen-/Prüfsummenfelder gibt). Deshalb sind mehrere
> Programme so wertvoll.

---

## Schritt 4 – Erste Analyse in Wireshark

- **Filter** auf die ST5-IP setzen: `ip.addr == 192.168.178.50`
- Rechtsklick auf ein Paket → **Follow → TCP/UDP Stream**: zeigt den Inhalt.
- Worauf achten:
  - **Klartext?** JSON/HTTP/ASCII-Kommandos sind ideal (leicht nachzubauen).
  - **Binär?** Auf wiederkehrende Muster achten, die sich nur in der
    Programmnummer unterscheiden (Byte-Diff zwischen `03/04/05`).
  - **Längenfeld / Prüfsumme / Sequenznummer** am Anfang/Ende der Nachrichten.
  - **Port & Transport** (TCP vs. UDP), Discovery (mDNS/Broadcast) beim Verbinden.

---

## Schritt 5 – Was ich von dir brauche

Zum Dekodieren und für den späteren Client brauche ich:
1. **Ergebnis Schritt 0** (lokal/Cloud).
2. **IP/Ports** der ST5 (Schritt 1).
3. Die **gelabelten Mitschnitte** aus Schritt 3 (gern als ZIP, ggf. um private
   Daten bereinigt – MAC/IP sind für die Analyse aber hilfreich und unkritisch).

Damit leite ich das Befehlsformat ab und wir bauen einen kleinen
**VOCO-Client** (Senden der Programm-Befehle), den das Gateway nutzt.

> ⚠️ **Sicherheit:** Testbefehle lösen **echtes Läuten** aus. Tests in Zeiten
> legen, in denen Läuten unkritisch ist, bzw. mit der Gemeinde abstimmen.
> Niemals Tokens/Zugangsdaten aus Mitschnitten ins Repository committen.

Siehe Gesamtkonzept: [`Konzept.md`](Konzept.md), Abschnitt 4 (Variante B).
