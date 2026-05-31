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

Zwei Dateien `wlan-133…`, `wlan-135…` (Format: *modified pcap*, Magic `a1b2cd34`,
24-Byte-Record-Header, linktype **105 = IEEE 802.11**).

Sauber ausgewertet (288 bzw. 310 Pakete):
- Frames sind **unverschlüsselt/lesbar** (kein WPA-Problem).
- **Aber: kein einziges Paket zu/von `192.168.178.151`** enthalten.
- Inhalt = nur **unbeteiligter Hintergrundverkehr** anderer Geräte:
  mDNS (`224.0.0.251:5353`), IPv6, ARP, IGMP, Broadcasts.

➡️ **Fazit:** Die App↔Steuerung-Verbindung (Port 25423) wurde **nicht erfasst**.
Der Mitschnitt traf nicht den richtigen Pfad/Zeitpunkt. Es ist **kein**
Verschlüsselungsproblem – wir brauchen einen Mitschnitt, der die unicast-
TCP-Verbindung Handy↔VOCO **tatsächlich enthält**.

> Hinweis: Eine frühere Notiz hatte diese Dateien fälschlich als
> „WPA2-verschlüsselt" eingestuft. Das war ein Auswertungsfehler und ist
> hiermit korrigiert.

## Offene Punkte / nächste Schritte

1. **Mitschnitt mit echtem VOCO-Verkehr** erzeugen (Anleitung:
   [`Mitschnitt-Klartext.md`](Mitschnitt-Klartext.md)). Wichtig: vor dem Hochladen
   prüfen, dass `192.168.178.151:25423` enthalten ist (Wireshark-Filter
   `tcp.port == 25423`).
2. Diese Verbindung analysieren → Befehl zum Auslösen eines Programms.
3. Erst danach: Referenz-Client + Mapping ChurchTools-Veranstaltung → Programm.

## Verifizierte Fakten (Stand jetzt)

- Steuerung erreichbar unter `192.168.178.151`, Hostname `HEW-VOCO.fritz.box`.
- Einziger auffälliger Port: **TCP 25423** (Steuer-Port, firewall-abgeschirmt).
- Noch **unbekannt**: das Anwendungsprotokoll auf 25423 sowie lokal/Cloud.
  (Frühere Aussagen zu einem konkreten Protokoll waren nicht belegt und wurden
  verworfen.)
