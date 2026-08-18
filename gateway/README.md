# Gateway-Dienst (Automatisches Läuten)

Liest die ChurchTools-Termine + die in der Extension konfigurierten Regeln und
löst zur richtigen Zeit das passende VOCO-Läuteprogramm per MQTT aus.
Läuft dauerhaft auf dem **Dauer-PC vor Ort** (braucht Internet).

## Einrichtung

```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
cp .env.example .env      # und ausfüllen (CT_BASE_URL, CT_LOGIN_TOKEN)
```

`CT_LOGIN_TOKEN` = Login-Token eines (technischen) ChurchTools-Benutzers.
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
| `churchtools.py` | ChurchTools-API-Client (Termine/Events) |
| `config.py` | lädt Gerät + Regeln aus ChurchTools (oder .env) |
| `voco_mqtt.py` | MQTT-Client + CLI (`list`/`status`/`start`/`stop`) |
