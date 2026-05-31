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

## Offene Punkte / nächste Schritte

1. Vollständiger Portscan `nmap -p- -T4 192.168.178.151`.
2. Port 80 gezielt prüfen (Browser `http://192.168.178.151`, `nmap -p80 -sV -Pn`).
3. **Entscheidend:** Datenverkehr **während der App-Nutzung** mitschneiden, um
   Port, Protokoll, Richtung (lokal vs. Cloud) und ggf. Authentifizierung zu sehen.
   - Option: **Fritz!Box-Paketmitschnitt** unter `http://fritz.box/html/capture.html`
     (eingebaut, kein Zusatztool) – während App-Aktionen aufnehmen.
   - Option: Windows-PC als **Mobiler Hotspot**, Handy darüber, Wireshark mitlaufen.
4. Lokal/Cloud-Test mit der App (Internet aus, WLAN an).
