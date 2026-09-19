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
`0x24→:`, `0x25→ß`, `0x26→Ä`, `0x27→Ö`, `0x28→Ü`, `0x29→ä`, `0x2A→ö`, `0x2B→ü`.

> Hier stand bis Version 26.8 `0x30→ö`, `0x31→ü` – das sind aber die **Ziffern
> 0 und 1**, und Programmnamen enthalten Ziffern („… - 1 min."). Die Folge ist
> lückenlos von `0x24` bis `0x2B`; dezimal sind das 36 bis 43. Wer sie als
> 24, 25, … 29, 30, 31 weiterzählt, trifft bei den letzten beiden daneben.

Die Namen kommen als rohe Bytes. Gelesen werden sie **Byte für Byte**
(Latin-1), weil die Längenangaben im Listenformat Bytes zählen. Erst der fertig
geschnittene Name wird zurechtgerückt, und zwar in dieser Reihenfolge:

1. **UTF-8**, wenn die Bytefolge als solche aufgeht.
2. **DOS (CP437/CP850)**, sobald ein Byte aus `0x80`–`0x9F` vorkommt.
3. Sonst bleibt es bei **Latin-1**.

### Die Anlage benutzt die Folge ab `0x18`

Gemessen an einem echten Gerät: „TESTLÄUTEN" kommt als `TESTL` + **`0x1A`** +
`UTEN` an. Dieselben acht Zeichen gibt es also zweimal, zwölf Stellen
versetzt:

| Zeichen | Variante A | Variante B (in der Praxis) |
|---|---|---|
| `:` | `0x24` | `0x18` |
| `ß` | `0x25` | `0x19` |
| `Ä` | `0x26` | **`0x1A`** |
| `Ö` | `0x27` | `0x1B` |
| `Ü` | `0x28` | `0x1C` |
| `ä` | `0x29` | `0x1D` |
| `ö` | `0x2A` | `0x1E` |
| `ü` | `0x2B` | `0x1F` |

Beide werden umgesetzt. Gefahrlos ist das, weil `0x18`–`0x1F` Steuerzeichen
sind, die in einem Programmnamen nie vorkommen.

### Umlaute kommen als DOS-Bytes

Die Steuerbyte-Tabelle oben ist nicht der einzige Weg, auf dem Umlaute
ankommen. In der Praxis schickt die Anlage sie im **DOS-Zeichensatz**:

| Zeichen | Byte | | Zeichen | Byte |
|---|---|---|---|---|
| `Ä` | `0x8E` | | `ä` | `0x84` |
| `Ö` | `0x99` | | `ö` | `0x94` |
| `Ü` | `0x9A` | | `ü` | `0x81` |
| `ß` | `0xE1` | | | |

„TESTLÄUTEN" kommt also als `TESTL` + `0x8E` + `UTEN` an. In Latin-1 ist `0x8E`
ein **unsichtbares Steuerzeichen** – die Anzeige zeigte deshalb ein leeres
Kästchen, obwohl der Name vollständig übertragen wurde.

Der Bereich `0x80`–`0x9F` ist der verlässliche Fingerzeig: Dort stehen in
Latin-1 ausschließlich Steuerzeichen, die in einem Programmnamen nie vorkommen.
Taucht eines auf, ist der Text DOS-kodiert. CP437 und CP850 sind in diesem
Bereich identisch, ebenso beim `ß` – sie müssen also nicht auseinandergehalten
werden.

Bleibt trotzdem ein Zeichen übrig, das sich nicht zuordnen lässt, nennt das
Ereignis-Log seinen Zahlenwert. Dann lässt sich die Tabelle gezielt ergänzen,
statt erneut zu raten.
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
