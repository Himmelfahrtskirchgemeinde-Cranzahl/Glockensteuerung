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

⚠️ **Portscans sind bei diesem Gerät NICHT verlässlich** (Messrauschen):

- **Lauf A:** meldet nur `25423/tcp filtered`.
- **Lauf B (Wiederholung):** meldet `Warning: giving up on port because
  retransmission cap hit (6)` und **18 völlig andere** „filtered" Ports
  (4513, 7391, 10269, 11268, 13236, 15819, 17899, 18509, 19083, 22562,
  25297, 27744, 32368, 34667, 39832, 45018, 46884, 60084) – **25423 ist nicht dabei**.

**Deutung:** Das Gerät bzw. die Fritz!Box **drosselt/verwirft** Scan-Pakete
(Rate-Limiting). Dadurch markiert nmap bei jedem Lauf **zufällig andere** Ports
als „filtered". Die Ergebnisse sind **Artefakte, kein echter Portzustand**.
→ Der Steuer-Port lässt sich **per Scan nicht** zuverlässig bestimmen
(auch die frühere Annahme „25423" ist damit **nicht belegt**).

➡️ **Konsequenz:** Portscanning als Methode verworfen. Der echte Port und das
Protokoll müssen aus einem **Mitschnitt des App-Verkehrs** ermittelt werden.

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
   [`Mitschnitt-Klartext.md`](Mitschnitt-Klartext.md)). Filter im Mitschnitt nicht
   auf einen Port festlegen, sondern auf die **Geräte-IP**: `ip.addr == 192.168.178.151`.
2. Daraus den **echten Port** und das **Protokoll** ablesen, dann den Befehl zum
   Auslösen eines Programms.
3. Erst danach: Referenz-Client + Mapping ChurchTools-Veranstaltung → Programm.

## Verifizierte Fakten (Stand jetzt)

- Steuerung erreichbar unter `192.168.178.151`, Hostname `HEW-VOCO.fritz.box`.
- Kommunikation lokal im LAN (Gerät hängt an der Fritz!Box).
- **Unbekannt:** der Steuer-Port und das Anwendungsprotokoll.
  Portscans sind wegen Rate-Limiting **unbrauchbar** (s. o.). Frühere Aussagen zu
  Port `25423` und zu einem konkreten Protokoll waren **nicht belegt** und sind
  verworfen.
- Klärung nur über einen **Verkehrsmitschnitt der App** möglich.
