# Anleitung: ChurchTools ⇄ VOCO-futura ST5

Diese Anleitung führt komplett durch die Einrichtung – von der Extension in
ChurchTools bis zum automatischen Läuten. Sie ist bewusst ausführlich; für den
schnellen Überblick genügen die **fett** markierten Schritte.

**Das Projekt hat zwei Teile:**

1. **ChurchTools-Extension** (Modul im Browser) – Bedienung + Einstellungen:
   Programme manuell auslösen, Gerät hinterlegen, Automatik-Regeln pflegen.
2. **Gateway-Dienst** (kleines Programm, läuft dauerhaft) – löst die Programme
   **automatisch** zur Termin-Zeit aus.

> **Muss der Gateway auf einem Kirchen-PC laufen?** Nein. Er muss nur **dauerhaft
> laufen und Internet haben** – das kann ein Raspberry Pi, ein kleiner Server/VPS
> oder ein vorhandener Dauer-PC sein (egal wo). ChurchTools selbst kann keine
> Hintergrund-Aufgaben ausführen, deshalb braucht die **Automatik** dieses eine
> laufende Programm. Das **manuelle** Läuten aus ChurchTools funktioniert dagegen
> ganz ohne Gateway.

---

## Kompatibilität

- ✅ **Aktuell unterstützt:** Läutesteuerungen der Reihe **HEW VOCO-futura**
  (mit LAN/WLAN-Modul und `hew-voco.de`-Portal, z. B. **ST5**).
- 🔜 **Geplant:** weitere HEW-Systeme sowie Steuerungen **anderer Hersteller**.
- 🔜 **Später:** eine **universelle**, herstellerübergreifende Lösung.

---

## Voraussetzungen

- ChurchTools-Zugang mit **Administrator-Rechten** (zum Installieren der Extension).
- Die **VOCO-Seriennummer** (z. B. `VH-xxxxxx`) und das **Geräte-Passwort**.
  (Beides identifiziert euer Gerät beim HEW-Broker. Quelle: HEW / euer
  VOCO-Portalzugang. Behandelt das Passwort wie einen Schlüssel.)
- Am **VOCO-Gerät** je Läute-Anlass ein **„Sofort-PGS"** angelegt
  (z. B. `Gottesdienstgeläut`) – siehe Teil 2.
- Für den Gateway: irgendein **dauerhaft laufender Rechner mit Internet**.

### Zugangsdaten ermitteln: Seriennummer & Geräte-Passwort

Für die Anbindung braucht ihr zwei Werte eures Geräts:

- **Seriennummer** (Form `VH-xxxxxx`): steht auf dem **Typenschild** der Steuerung
  und wird auch im HEW-Portal angezeigt.
- **Geräte-Passwort:** nicht offiziell dokumentiert. Es steckt im **Quelltext der
  eingeloggten Geräteseite** im HEW-Portal – so kommt ihr dran:
  1. Auf **`hew-voco.de`** mit eurem Konto **einloggen** und euer Gerät öffnen.
     (Das Konto muss für dieses Gerät freigeschaltet sein – ggf. Freischaltcode/HEW.)
  2. **Seitenquelltext anzeigen:** Rechtsklick → „Seitenquelltext anzeigen"
     (bzw. `Strg`+`U`), oder `F12` → Bereich *Elements/Quelltext*.
  3. Nach `serialNumber` und `mqttDeivcePw` suchen (`Strg`+`F`):
     ```js
     var serialNumber = "VH-xxxxxx";
     var mqttDeivcePw = "…euer Geräte-Passwort…";
     ```
  4. Beide Werte in der **Extension** (unter „Gerät") bzw. in `gateway/.env`
     (`VOCO_SERIAL`, `VOCO_DEVICE_PW`) eintragen.

> ⚠️ Das Geräte-Passwort ist ein **Geheimnis** – wie einen Schlüssel behandeln,
> nicht teilen oder committen. Ändert HEW das Portal, kann sich der Weg ändern.

---

## Teil 1 – Extension bauen und in ChurchTools installieren

Ihr braucht am Ende eine **ZIP-Datei**, die ihr in ChurchTools hochladet. Es gibt
zwei Wege, an diese ZIP zu kommen.

### Weg A (empfohlen): ZIP von GitHub bauen lassen – ohne eigene Software

GitHub baut die Extension automatisch. So kommt ihr an die ZIP:

**Als sauberer Einzeldownload über ein Release (empfohlen):**

1. Im Repository einen **Versions-Tag** setzen, z. B. `v0.1.0`:
   - Auf GitHub: **Releases → „Draft a new release" → „Choose a tag"** → `v0.1.0`
     eingeben → **Publish release**.
   - (Oder per Git: `git tag v0.1.0 && git push origin v0.1.0`.)
2. Der Workflow **„ChurchTools-Extension bauen (ZIP)"** startet automatisch, baut
   die Extension und **hängt die fertige ZIP an das Release**.
3. Unter **Releases** die Datei `glockensteuerung-vX.Y.Z-<hash>.zip` herunterladen.
   **Das ist die Datei für ChurchTools.**

**Oder als schneller Test-Build (ohne Tag):**

1. Auf GitHub in den Tab **„Actions"**.
2. Links den Workflow **„ChurchTools-Extension bauen (ZIP)"** wählen →
   **„Run workflow"** (Knopf rechts) → Branch wählen → **Run**.
3. Nach ~1 Minute den Lauf öffnen → unten unter **„Artifacts"**
   `glockensteuerung-extension` herunterladen.
4. ⚠️ **Wichtig:** Dieser Download ist selbst ein ZIP (so macht es GitHub). Erst
   **entpacken** – darin liegt die eigentliche `glockensteuerung-…zip`. **Diese
   innere ZIP** kommt nach ChurchTools.

### Weg B: Selbst bauen (wenn Node.js vorhanden)

```bash
cd extension
npm install
npm run deploy        # baut + packt -> extension/releases/glockensteuerung-*.zip
```

### Die ZIP in ChurchTools installieren

1. In ChurchTools als Administrator: **Admin/Einstellungen → Erweiterungen**
   (Custom Modules).
2. **Erweiterung hochladen** → die `glockensteuerung-*.zip` auswählen → installieren.
3. Das Modul **„Glockensteuerung"** erscheint anschließend in der Navigation.

> Der Modul-Key ist `glockensteuerung`. Er muss mit der Einstellung `VOCO_EXT_KEY`
> des Gateways übereinstimmen (Standard passt bereits).

---

## Teil 2 – Gerät und Regeln in der Extension einrichten

Öffnet in ChurchTools das Modul **„Glockensteuerung"**.

### 2.1 Sofort-PGS am VOCO-Gerät anlegen (einmalig, am Gerät)

Damit die Automatik ein Programm auslösen kann, muss es als **Sofort-PGS**
existieren. Am VOCO-Touchscreen bzw. im HEW-Portal je Anlass einen Sofort-PGS
mit sprechendem Namen anlegen, z. B.:

- `Gottesdienstgeläut` (die passenden Glocken, gewünschte Dauer)
- `Vorläuten`, `Trauergeläut`, `Taufgeläut` …

### 2.2 Gerät hinterlegen

Im Modul unter **„Gerät"**:

- **Seriennummer** (z. B. `VH-xxxxxx`)
- **Geräte-Passwort**
- **Broker-URL** bleibt `wss://hew-voco.de:8084/mqtt`

**Speichern & verbinden.** Oben sollte „Gerät online" erscheinen und unter
„Programme" eure Sofort-PGS auftauchen. Zum Testen einen Knopf **„Läuten"**
drücken (löst **echtes** Läuten aus – in unkritische Zeit legen!).

### 2.3 Automatik-Regeln anlegen

Unter **„Automatik-Regeln"** je Anlass eine Regel:

| Feld | Bedeutung |
|---|---|
| **Name** | frei, z. B. „Sonntagsgottesdienst" |
| **Kalender** | optional: nur Termine dieses Kalenders |
| **Veranstaltungsart** | optional: nur diese Kategorie (z. B. „Beerdigung") |
| **Läuteprogramm** | Name des Sofort-PGS, der ausgelöst wird |
| **Vorlauf (Min.)** | wie viele Minuten **vor** Terminbeginn geläutet wird |
| **Aktiv** | Regel ein/aus |

Kalender **und** Veranstaltungsart lassen sich kombinieren (beides gesetzt =
beide Bedingungen müssen zutreffen; nichts gesetzt = jeder Termin). **Regeln
speichern.**

---

## Teil 3 – Automatik-Gateway einrichten

Der Gateway liest eure ChurchTools-Termine + die Regeln und löst automatisch aus.

### 3.1 Wo laufen lassen?

Irgendein Gerät, das **dauerhaft an ist und Internet hat**:

- **Raspberry Pi** (günstig, stromsparend) – gute Dauerlösung.
- **Kleiner Server / VPS** (z. B. günstiger Root-/Cloud-Server).
- **Vorhandener Dauer-PC / Heimserver.**

Es muss **nicht** in der Kirche stehen – Steuerung und ChurchTools laufen über
das Internet.

### 3.2 ChurchTools-Login-Token besorgen

Der Gateway meldet sich mit einem **Login-Token** an ChurchTools an
(am besten ein eigener, technischer Benutzer):

- In ChurchTools: **Persönliche Einstellungen → Sicherheit/Berechtigungen →
  Login-Token** anzeigen/erzeugen. Der Benutzer braucht Leserechte auf die
  betreffenden Kalender/Veranstaltungen und das Modul.

### 3.3 Installieren

```bash
# Projekt holen (oder als ZIP von GitHub herunterladen)
git clone https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Uhrensteuerung.git
cd Uhrsteuerung/gateway

# Python-Umgebung + Abhängigkeiten
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Konfiguration
cp .env.example .env
# .env öffnen und ausfüllen:
#   CT_BASE_URL=https://EUREGEMEINDE.church.tools
#   CT_LOGIN_TOKEN=... (der Token aus 3.2)
# Gerät wird i. d. R. aus der Extension gelesen; alternativ VOCO_SERIAL/VOCO_DEVICE_PW setzen.
```

### 3.4 Testen (ohne dass etwas läutet)

```bash
python voco_mqtt.py status      # zeigt: Gerät online? + eure Programme
python scheduler.py --dry-run   # plant aus euren Terminen, löst NICHT aus (nur Anzeige)
```

Wenn `--dry-run` die richtigen Auslösungen anzeigt, ist alles korrekt verdrahtet.

### 3.5 Dauerbetrieb einrichten

**Linux (systemd)** – Datei `/etc/systemd/system/voco-gateway.service`:

```ini
[Unit]
Description=VOCO Glocken-Gateway
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/pfad/zu/Uhrsteuerung/gateway
ExecStart=/pfad/zu/Uhrsteuerung/gateway/.venv/bin/python scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now voco-gateway
sudo systemctl status voco-gateway      # Log prüfen
journalctl -u voco-gateway -f           # Live-Log
```

**Windows** – Aufgabenplanung: neue Aufgabe „Bei Systemstart" →
Programm `…\.venv\Scripts\python.exe`, Argument `scheduler.py`,
„Ausführen, auch wenn nicht angemeldet".

### 3.6 Ruhezeit & Sicherheit (empfohlen)

In der `.env`:

```
VOCO_QUIET=22:00-06:00     # in diesem Fenster wird NIE ausgelöst
```

- Der Gateway merkt sich ausgelöste Termine (`state.json`) → **kein Doppel-Läuten**.
- Verpasste Auslösungen (> 2,5 min zu spät) werden **nicht** nachgeholt.

---

## Teil 4 – Sicherheit (bitte beachten)

- **Geräte-Passwort & Login-Token sind Geheimnisse.** Nie in Chats, E-Mails oder
  ins Repository. In der Extension liegen sie zugriffsbeschränkt in ChurchTools,
  im Gateway in der lokalen `.env` (durch `.gitignore` ausgeschlossen).
- **Modulzugriff einschränken:** Wer das Modul öffnen kann, kann läuten. Rechte in
  ChurchTools entsprechend vergeben.
- **Testen immer in unkritischen Zeiten** – jeder „Läuten"-Knopf ist echt.

---

## Feedback & automatische Fehler-Benachrichtigung (wichtig für Tests mit mehreren Personen)

Da mehrere Leute testen, sammeln wir Rückmeldungen und Fehler **zentral**.

### In der Extension
- Unten rechts gibt es einen **Feedback-Knopf** mit Formular. Zusätzlich meldet die
  Extension **Fehler automatisch**.
- **Ohne** konfigurierten Endpunkt: Feedback öffnet eine **E-Mail** an
  `josua.hess@icloud.com` (automatische Fehlermeldung ist dann nur lokal sichtbar,
  da ein Browser nicht ungefragt mailen kann).
- **Mit** zentralem Endpunkt (empfohlen): Feedback **und** automatische Fehler
  gehen per POST an eine zentrale Adresse → ein Postfach für alle Tester.

**Zentralen Endpunkt einrichten (einmalig, empfohlen):**
1. Bei einem Formular-zu-E-Mail-Dienst ein Formular anlegen (z. B.
   **Formspree** oder **Web3Forms**, kostenlos) mit Zieladresse
   `josua.hess@icloud.com`. Man erhält eine **Endpunkt-URL**.
2. Diese URL im GitHub-Repo als **Variable** hinterlegen:
   *Settings → Secrets and variables → Actions → Variables →* `VITE_FEEDBACK_URL`.
3. Extension über den GitHub-Workflow neu bauen (die URL wird eingebacken).
   Ab dann landen Feedback + automatische Fehler dort.

### Im Gateway (automatische Fehler-Mails)
Der Gateway läuft dauerhaft; er mailt bei Fehlern an `EMAIL_TO`
(Standard `josua.hess@icloud.com`). Dazu in der `gateway/.env` die SMTP-Daten
eines Postausgangs eintragen (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, …; siehe
`gateway/.env.example`). Ohne SMTP bleibt es still (nur Log). Eine **Spam-Sperre**
sendet dieselbe Fehlerart höchstens einmal pro Stunde.

### Datenschutz
Berichte enthalten **keine** Passwörter/Token; die Seriennummer wird **maskiert**.
Angehängt werden nur technische Angaben (Instanz-Host, Version, letzte Ereignisse).

---

## Teil 5 – Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| „Gerät offline" in der Extension | Seriennummer/Passwort falsch, oder VOCO gerade nicht mit dem HEW-Broker verbunden (Internet am Gerät prüfen). |
| Keine Programme in der Liste | Am Gerät sind (noch) keine **Sofort-PGS** angelegt. |
| `--dry-run` zeigt keine Auslösungen | Regeln passen nicht (Kalender-ID/Veranstaltungsart), oder im Zeitraum liegen keine Termine. Kalender/Kategorie-Schreibweise prüfen. |
| ChurchTools-Login schlägt fehl | `CT_BASE_URL`/`CT_LOGIN_TOKEN` prüfen; Benutzer braucht Leserechte. |
| Extension lädt lokal nicht (`npm run dev`) | CORS in ChurchTools erlauben: System-Einstellungen → Integrationen → API → CORS → Origin `http://localhost:5173`. |
| Endpunkte/Feldnamen weichen ab | ChurchTools-API-Versionen unterscheiden sich – gegen `https://<gemeinde>.church.tools/api` (Swagger) prüfen; ggf. `gateway/churchtools.py` anpassen. |

---

## Anhang – Für mehrere Kirchgemeinden

- Jede Gemeinde installiert die **Extension** und trägt ihr Gerät + Regeln ein.
- Ein **Gateway pro Gemeinde** (eigener Login-Token + Gerät) ist am einfachsten und
  sichersten. Ein zentraler Multi-Mandanten-Dienst ist möglich, erfordert aber
  sorgfältiges Speichern fremder Zugangsdaten – und idealerweise eine **offizielle
  Freigabe/Schnittstelle von HEW**.
- Hinweis: Die Steuerung basiert auf dem (nachgebauten) HEW-Cloud-Protokoll; für
  einen dauerhaften Produktbetrieb bei Dritten sollte HEW eingebunden werden.
