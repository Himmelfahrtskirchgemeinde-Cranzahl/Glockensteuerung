# VOCO MQTT-Protokoll (app.hew-voco.de) — belegt aus dem Web-App-Quelltext

Quelle: JavaScript der eingeloggten Portalseite `app.hew-voco.de`
(Paho-MQTT-Client). Damit ist die Steuerung **belegt**, nicht vermutet.

> 🔐 **Secrets:** Seriennummer + **Geräte-Passwort** zusammen erlauben das
> Auslösen der Glocken. **Nie** ins Repo/Chat. Nur lokal in `.env`
> (siehe [`../.env.example`](../.env.example)). In diesem Dokument stehen nur
> Platzhalter `<SERIAL>` / `<DEVPW>`.

## Transport / Verbindung

| Parameter | Wert |
|---|---|
| Broker-Host | `hew-voco.de` |
| Port | `8084` |
| Transport | **MQTT über WebSocket (WSS/TLS)**, WS-Pfad `/mqtt` |
| Broker-Login | Benutzer `hewWeb`, Passwort `vocoWeb` (fest, für alle Web-Clients) |
| Client-ID | `<SERIAL>-web` (frei wählbar) |
| Optionen | `cleanSession: true`, `keepAlive: 600 s` |

## Adressierung (Topic-Schema)

**Basis-Topic:** `hew/voco/<SERIAL><DEVPW>` — Seriennummer und Geräte-Passwort
**direkt aneinandergehängt** (kein Trenner). Beispiel-Struktur:
`hew/voco/<SERIAL><DEVPW>/<subtopic>`

Der Web-Client abonniert `hew/voco/<SERIAL><DEVPW>/#`.

## Eingehend (Gerät → Client)

| Subtopic | Inhalt |
|---|---|
| `/connection` | `1` = online, sonst offline |
| `/syncdata` | proprietär kodiert: Namenslisten `sPGS`, `programsteps`, `pgsmodes`, `melodies` |
| `/syncinfo` | Status: Glocken, Uhrzeit, Zeitempfang, nächste PGS … (kompaktes Textformat) |
| `/sendpgsD` | Antwort auf `list`: startbare PGS + stoppbare PGS (längenpräfix-kodiert) |
| `/sw` | `enable`/`disable` (Schlagwerk) |
| `/auto` | `enable`/`disable` (Läuteautomatik) |

## Ausgehend (Client → Gerät) — die Befehle

Alle als MQTT-`publish`, `retained=false`, an `hew/voco/<SERIAL><DEVPW>` + Subtopic:

| Zweck | Subtopic | Payload |
|---|---|---|
| **Programm/PGS starten** | `/playpgsD` | `START:<PGS-Name>:INSTANT` (sofort) |
| Programm zeitversetzt starten | `/playpgsD` | `START:<PGS-Name>:<Sekunden seit 0 Uhr>` |
| **Startbare Liste anfordern** | `/playpgsD` | `list` (Antwort auf `/sendpgsD`) |
| Programm stoppen | `/playpgsD` | `STOP:<Name>` bzw. `STOP:ALL` |
| Statusinfo anfordern | `/fetchinfo` | `EN` (Antwort auf `/syncinfo`) |
| Datenlisten anfordern | `/fetchdata` | `1` (Antwort auf `/syncdata`) |
| Schlagwerk ein/aus | `/swD` | `EN` / `DIS` |
| Automatik ein/aus | `/autoD` | `EN` / `DIS` |
| Einzelne Glocke sperren | `/gl/block` | `<Index>` |

> **Typischer Ablauf zum Auslösen:**
> 1. `list` → `/playpgsD`, Antwort auf `/sendpgsD` lesen → Namen der startbaren
>    (Sofort-)PGS.
> 2. `START:<Name>:INSTANT` → `/playpgsD`.

## Kodierungs-Eigenheit (Sonderzeichen)

PGS-Namen können Steuerbytes statt Umlauten enthalten (Mapping aus dem JS):
`0x24→:`, `0x25→ß`, `0x26→Ä`, `0x27→Ö`, `0x28→Ü`, `0x29→ä`, `0x30→ö`, `0x31→ü`.
→ **Zum Anzeigen** dekodieren, **zum Senden** den **rohen** Namen (wie empfangen)
unverändert verwenden. Der Referenz-Client macht genau das.

## Bewertung für die ChurchTools-Anbindung

- ✅ Sauberer, verkabelungsfreier Weg: Gateway → MQTT (WSS) → HEW-Broker → ST5.
- ✅ Funktioniert überall mit Internet (nicht nur im LAN).
- ⚠️ Läuft über die **HEW-Cloud** (Broker `hew-voco.de`). Abhängigkeit von deren
  Verfügbarkeit; für vollen Portal-Funktionsumfang ist lt. Handbuch ein
  **Freischaltcode** nötig — ob das reine MQTT-Auslösen davon betroffen ist,
  beim Test prüfen.
- 🔒 Autorisierung nur über das Geheimnis im Topic (Seriennummer+Geräte-PW) und
  die gemeinsamen Broker-Creds. Kein persönlicher Account nötig → Secret schützen!

## Vorgehen: „Sofort-PGS" als Auslöse-Ziele

Empfehlung: am Gerät/Portal je Läute-Anlass **einen Sofort-PGS** anlegen
(z. B. „Gottesdienstgeläut", „Vorläuten", „Trauergeläut"). Der Gateway löst dann
per `START:<Name>:INSTANT` genau diesen aus. Damit bleibt die Läutelogik (welche
Glocken, wie lange) im Gerät, und ChurchTools steuert nur **wann + welcher Anlass**.
