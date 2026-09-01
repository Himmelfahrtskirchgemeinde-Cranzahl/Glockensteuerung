# Gateway-Dienst (Automatisches Läuten)

Liest die ChurchTools-Termine + die in der Extension konfigurierten Regeln und
löst zur richtigen Zeit das passende VOCO-Läuteprogramm per MQTT aus.

Läuft auf **irgendeinem dauerhaft laufenden Rechner mit Internet** – das muss
**nicht** in der Kirche stehen: Raspberry Pi, kleiner Server/VPS oder ein
vorhandener Dauer-PC. (Steuerung und ChurchTools laufen über das Internet.)

> **📖 Komplette Einrichtung Schritt für Schritt: [`../ANLEITUNG.md`](../ANLEITUNG.md)**

> **🛡️ Simulation:** `python scheduler.py --dry-run` plant und protokolliert,
> löst aber **nicht** aus. Dauerhaft: `VOCO_SIMULATION=1` in der `.env`.

## Einrichtung

```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
cp .env.example .env      # und ausfüllen (CT_BASE_URL, CT_LOGIN_TOKEN)
```

`CT_LOGIN_TOKEN` = Login-Token eines (technischen) ChurchTools-Benutzers.

**Benoetigte Rechte:** Der Benutzer muss die Kategorien des Moduls
„Glockensteuerung" **lesen** duerfen (Geraet + Regeln) und in der Kategorie
`steuerung` zusaetzlich **schreiben** duerfen. Das Schreibrecht braucht nur das
Lebenszeichen (Heartbeat), das der Dienst alle 2 Minuten hinterlegt, damit die
Extension anzeigen kann, ob die Automatik ueberhaupt laeuft. Fehlt das Recht,
laeuft der Dienst normal weiter und laeutet wie gewohnt - er schreibt dann nur
eine Warnung ins Log, und die Extension meldet „Gateway nicht erreichbar".

Kommt der **E-Mail-Versand** zum Einsatz, braucht der Benutzer zusaetzlich
**Leserecht** auf die Kategorie `email` - dort liegen die Zugangsdaten zum
Postausgang. Diese Kategorie sollte **sonst niemand** lesen duerfen: Sie
enthaelt ein Passwort.

## E-Mail-Versand

Die Extension kann selbst keine E-Mail senden - ein Browser spricht kein SMTP.
Sie stellt Nachrichten nur in einen Postausgang; verschickt werden sie hier.

Die Zugangsdaten koennen in der Extension gepflegt werden (Untermenue
„E-Mail-Versand", nur mit dem Recht „Erweiterung verwalten"). Sie haben Vorrang
vor der `.env`, damit sich der Postausgang aendern laesst, ohne an den Server zu
muessen. Fehlt dort ein Host, gelten die `SMTP_*`-Werte aus der `.env`.

Einmal je Minute holt der Dienst, was eingestellt wurde, verschickt es und leert
den Ausgang - auch wenn einzelne Nachrichten nicht rausgingen. Sonst versuchte
er es im Minutentakt erneut und wuerde das Postfach fluten, sobald es doch
klappt; Fehlschlaege stehen im Log.
Das Gerät (Seriennummer + Passwort) wird bevorzugt in der **Extension**
konfiguriert; der Gateway liest es von dort. Alternativ in `.env` eintragen.

## Testen (ohne Läuten)

```bash
python voco_mqtt.py status        # Verbindung + startbare PGS anzeigen
python scheduler.py --dry-run     # plant und zeigt Auslösungen, löst NICHT aus
```

## Dauerbetrieb

```bash
python scheduler.py
```

Für Autostart als Dienst: systemd-Unit (Linux) oder Aufgabenplanung (Windows).
Beispiel systemd `/etc/systemd/system/voco-gateway.service`:

```ini
[Unit]
Description=VOCO Gateway
After=network-online.target

[Service]
WorkingDirectory=/pfad/zu/gateway
ExecStart=/pfad/zu/gateway/.venv/bin/python scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Sicherheit / Verhalten

- **Kein Doppel-Läuten:** ausgelöste Termine werden in `state.json` gemerkt.
- **Ruhezeit:** optional `VOCO_QUIET=22:00-06:00` in `.env` → in dem Fenster wird
  nie ausgelöst.
- **Fail-safe:** verpasste Auslösungen (> 2,5 min zu spät) werden übersprungen,
  nicht nachgeholt.
- 🔐 `.env` und `state.json` nicht committen (via `.gitignore` ausgeschlossen).

## Dateien

| Datei | Zweck |
|---|---|
| `scheduler.py` | Hauptdienst (Planung + Auslösung) |
| `churchtools.py` | ChurchTools-API-Client (Kalender-Termine) |
| `config.py` | lädt Gerät + Regeln aus ChurchTools (oder .env) |
| `voco_mqtt.py` | MQTT-Client + CLI (`list`/`status`/`start`/`stop`) |
| `tls.py` | Wurzelzertifikate für MQTT und E-Mail |
| `diagnose.py` | prüft, warum eine verschlüsselte Verbindung scheitert |

## Wenn die Verbindung am Zertifikat scheitert

Unter Windows meldet Python beim Verbindungsaufbau haeufig:

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: unable to get local issuer certificate
```

Dahinter stecken zwei verschiedene Ursachen, die dieselbe Meldung erzeugen.
Welche es ist, sagt die Diagnose:

```
python -m diagnose
```

Sie nennt die benutzten Zertifikatsquellen und vor allem, **wer das Zertifikat
des Brokers ausgestellt hat**. Zugangsdaten braucht sie keine.

**Aussteller ist eine öffentliche Stelle** (Let's Encrypt, DigiCert, Sectigo …):
Dann fehlen nur Wurzelzertifikate. Python bringt unter Windows keine mit. Der
Dienst nutzt deshalb das Bundle von `certifi`, das mit den Abhängigkeiten
installiert wird. Bleibt der Fehler:

```
pip install --upgrade certifi
```

**Aussteller ist ein Virenscanner, eine Firewall oder die eigene Firma:** Dann
wird die Verbindung aufgebrochen und im laufenden Betrieb neu ausgestellt.
`certifi` kann davon nichts wissen — und wird es auch nie. Deren Zertifikat
exportieren (Windows-Zertifikatsspeicher, „Vertrauenswürdige
Stammzertifizierungsstellen", Format Base-64/PEM) und den Pfad eintragen:

```
VOCO_CA_BUNDLE=C:\Pfad\zur\firmen-ca.pem
```

Geprüft wird dann gegen den Systemspeicher, `certifi` **und** diese Stelle — die
Prüfung bleibt also vollständig erhalten. Sie abzuschalten ist nicht vorgesehen:
Über diese Verbindung läuft das Läuten, sie gehört abgesichert. Ein Gateway, das
jedes Zertifikat annimmt, ließe sich mit einem untergeschobenen Broker
fernsteuern.

Meldet die Diagnose stattdessen, dass gar keine Verbindung zustande kommt, ist
es kein Zertifikatsproblem: Dann sperrt eine Firewall den Port.

