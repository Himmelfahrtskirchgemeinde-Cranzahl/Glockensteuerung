# Analyse-Befunde: VOCO-futura ST5 im Netzwerk

Laufendes Protokoll der Erkenntnisse aus der Selbst-Analyse (Variante B).

---

## Geräte-Eckdaten

| Eigenschaft | Wert |
|---|---|
| IP | `192.168.178.151` |
| Hostname | `HEW-VOCO.fritz.box` (eindeutig die HEW VOCO-Steuerung) |
| MAC | `56:80:E1:00:04:3D` (lokal verwaltet, kein Hersteller-OUI) |
| Router | AVM Fritz!Box |
| Status | online, antwortet (echter TCP-Stack) |

## Portscan #1 – Quick scan (nmap `-T4 -F`, Top-100-Ports), 2026-05-31

```
Not shown: 97 closed tcp ports (reset)
PORT     STATE    SERVICE
80/tcp   filtered http
139/tcp  filtered netbios-ssn
3389/tcp filtered ms-wbt-server
```

**Deutung:**
- 97 Ports `closed` (RST) → Gerät reagiert aktiv.
- Port **80 `filtered`** (kein RST, Paket verworfen) → Hinweis auf ein
  **per Firewall abgeschirmtes Web-Interface** (anders als die 97 RST-Ports).
- 139/3389 `filtered` → typisches Droppen gängiger Angriffsports.
- **Noch offen:** vollständiger Portscan (`-p-`, alle 65535) steht aus –
  der Steuer-Port könnte ein hoher Port sein.

## Portscan #2 – Vollständiger Scan (nmap `-p-`), 2026-05-31

```
Not shown: 65534 closed tcp ports (reset)
PORT       STATE     SERVICE
25423/tcp  filtered  unknown
```

**Deutung:**
- Von allen 65535 TCP-Ports ist **nur `25423/tcp` „filtered"** (alle übrigen `closed`).
  → Sehr wahrscheinlich der **Steuer-Port** der ST5; per Firewall gegen Scans
  abgeschirmt, nimmt aber die App an.
- Port 80 ist auch im **Browser vom PC nicht erreichbar** → kein offenes Web-Interface.

## Mitschnitt-Versuch #1 (Fritz!Box, WLAN), 2026-05-31

- Zwei Dateien `wlan-133…`, `wlan-135…` (pcap, linktype **105 = IEEE 802.11**).
- **Ergebnis: alle Daten-Frames sind WPA2-verschlüsselt** → IP/TCP-Nutzdaten
  **nicht lesbar**. Aus diesen Mitschnitten lässt sich das Protokoll nicht ableiten.

## Offene Punkte / nächste Schritte

1. **Lesbaren** Mitschnitt erzeugen (Klartext-IP statt verschlüsseltem 802.11):
   - **Variante A (empfohlen):** Windows-PC als *Mobiler Hotspot*, Handy darüber,
     mit **Wireshark** auf dem Hotspot-Adapter aufnehmen → entschlüsselte
     Ethernet/IP-Frames. Danach `.pcapng` hochladen.
   - **Variante B:** Fritz!Box-WLAN-Mitschnitt wiederholen, dabei das Handy-WLAN
     **trennen und neu verbinden** (4-Wege-Handshake aufzeichnen), dann in
     Wireshark mit dem **WLAN-Passwort** entschlüsseln (IEEE-802.11-Einstellungen).
2. Im lesbaren Mitschnitt: Verbindung zu `192.168.178.151:25423` analysieren
   (Protokoll, Befehl zum Auslösen eines Programms).
3. Erst danach: Referenz-Client + Mapping ChurchTools-Veranstaltung → Programm.

> **Hinweis zur Sorgfalt:** Frühere, nicht abgeschlossene Analyseläufe hatten zu
> verfrühten Protokoll-Aussagen geführt; diese wurden verworfen. Dieses Dokument
> enthält nur tatsächlich verifizierte Messergebnisse.
