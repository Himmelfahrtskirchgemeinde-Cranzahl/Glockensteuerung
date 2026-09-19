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
  1. Auf **`app.hew-voco.de`** mit eurem Konto **einloggen** und euer Gerät öffnen.
     (Das Konto muss für dieses Gerät freigeschaltet sein – ggf. Freischaltcode/HEW.)
  2. **Entwicklertools öffnen** mit `F12` und das Dokument **`(index)`** ansehen:
     im Reiter *Elemente/Sources* die Seite `(index)`, oder unter *Netzwerk/Network*
     den Eintrag `(index)` auswählen → *Antwort/Response*. (Alternativ `Strg`+`U`.)
  3. Ganz oben im inline-`<script>` stehen die beiden Werte (`Strg`+`F` zum Suchen):
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

**Fester Download-Link (einfachster Weg):**

Immer die aktuelle Fassung, der Link ändert sich nie:

<https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest/download/glockensteuerung.zip>

Herunterladen und **unverändert** in ChurchTools hochladen – kein Entpacken. Der
Link zeigt immer auf das neueste Release; welche Version das ist, steht dort im
Titel. Diesen Link kann man sich merken oder weitergeben.

**Eine bestimmte Version (Archiv):**

Unter **Releases** hat jede Version einen eigenen Eintrag („Version 26.8.0") mit
ihrem Changelog und der Datei `glockensteuerung.zip`. Welche Version darin
steckt, sagt der Titel – nur nötig, wenn ihr gezielt eine ältere Fassung
braucht.

**Oder als schneller Test-Build (ohne Tag):**

1. Auf GitHub in den Tab **„Actions"**.
2. Links den Workflow **„Erweiterung und Gateway bauen (ZIP)"** wählen →
   **„Run workflow"** (Knopf rechts) → Branch wählen → **Run**.
3. Nach ~1 Minute den Lauf öffnen → unten unter **„Artifacts"**
   `glockensteuerung-extension` herunterladen.
4. ⚠️ **Wichtig:** Dieser Download ist selbst ein ZIP (so macht es GitHub). Erst
   **entpacken** – darin liegen die eigentliche `glockensteuerung-…zip` für
   ChurchTools und die Programmdatei für Windows. **Die innere ZIP** kommt nach
   ChurchTools.

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
| **Termin-Titel** | optional: nur Termine mit **exakt** diesem Titel (z. B. „Gottesdienst") |
| **Läuteprogramm** | Name des Sofort-PGS, der ausgelöst wird |
| **Vorlauf (Min.)** | wie viele Minuten **vor** Terminbeginn geläutet wird |
| **Aktiv** | Regel ein/aus |

Kalender **und** Termin-Titel lassen sich kombinieren (beides gesetzt = beide
Bedingungen müssen zutreffen; nichts gesetzt = jeder Termin). **Regeln
speichern.**

Der Titel wird **exakt** verglichen – Groß-/Kleinschreibung und Leerzeichen am
Rand spielen keine Rolle, der Rest muss aber Zeichen für Zeichen stimmen. „Gottesdienst"
trifft deshalb **nur** Termine, die genau so heißen, und **nicht** zusätzlich
„Festgottesdienst". Für beide Anlässe legt man also zwei Regeln an.

> Früher stand hier die **Veranstaltungsart**. Die hängt in ChurchTools aber
> nicht am Termin, sondern an einer verknüpften Veranstaltung, und ist dort
> meist gar nicht gepflegt – solche Regeln griffen deshalb nie. Bestehende
> Regeln übernehmen den alten Eintrag automatisch als Termin-Titel; bitte
> einmal prüfen, ob er mit dem Titel im Kalender übereinstimmt.

---

## Teil 3 – Automatik-Gateway einrichten

Der Gateway liest eure ChurchTools-Termine + die Regeln und löst automatisch aus.

### 3.1 Wo laufen lassen?

Irgendein Gerät, das **dauerhaft an ist und Internet hat**:

- **Windows-PC, der ohnehin durchläuft** – dafür gibt es die fertige
  Programmdatei; es ist der einfachste Weg (3.3).
- **Raspberry Pi** (günstig, stromsparend) – gute Dauerlösung.
- **Kleiner Server / VPS** (z. B. günstiger Root-/Cloud-Server).

Es muss **nicht** in der Kirche stehen – Steuerung und ChurchTools laufen über
das Internet.

### 3.2 ChurchTools-Login-Token besorgen

Der Gateway meldet sich mit einem **Login-Token** an ChurchTools an
(am besten ein eigener, technischer Benutzer):

- In ChurchTools: **Persönliche Einstellungen → Sicherheit/Berechtigungen →
  Login-Token** anzeigen/erzeugen. Der Benutzer braucht Leserechte auf die
  betreffenden Kalender/Veranstaltungen und das Modul.

### 3.3 Windows: einrichten in fünf Minuten

Für Windows gibt es den Gateway **fertig gebaut** – ohne Python, ohne
Kommandozeile, ohne Aufgabenplanung.

1. **Herunterladen:**
   [`Glockensteuerung-Gateway.exe`](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest/download/Glockensteuerung-Gateway.exe)
   (der Link zeigt immer auf die neueste Fassung).
2. **Ablegen:** in einen eigenen Ordner, zum Beispiel
   `C:\Automationen\Glockensteuerung\gateway`. Wohin, ist frei – der Dienst
   merkt sich den Ort.
3. **Doppelklick** und **1** wählen: *Installieren*.

Dabei entsteht alles Weitere von selbst: der Ordner (falls nötig), die
Programmdatei darin, die `.env` mit den Zugangsdaten, der Windows-Dienst und
eine Verknüpfung **„Glockensteuerung"** im Startmenü – darüber sind
Einstellungen, Status und Protokoll später jederzeit erreichbar.



Gefragt wird dabei nur nach zwei Dingen:

| Frage | Antwort |
|---|---|
| Adresse von ChurchTools | `https://EUREGEMEINDE.church.tools` |
| Login-Token | der Token aus 3.2 |
| Simulation einschalten? | beim ersten Mal **ja** – dann wird nichts ausgelöst |

Das Programm probiert die Angaben **sofort aus** und sagt, was es vorfindet
(„Geräts VH-… gefunden, 3 aktive Regeln"). Erst danach schreibt es die Datei
`.env` in denselben Ordner. Ein Tippfehler fällt damit sofort auf und nicht
erst, wenn am Sonntag die Glocken schweigen.

Anschließend fragt Windows nach Administratorrechten – das ist für das Anlegen
des Dienstes nötig. Danach steht er in `services.msc` als
**Glockensteuerung Gateway**.

> **„Der Computer wurde durch Windows geschützt"** erscheint beim ersten Start,
> weil die Datei nicht mit einem gekauften Zertifikat signiert ist.
> *Weitere Informationen → Trotzdem ausführen.*

Was dann von selbst passiert:

- Der Dienst startet **beim Hochfahren des Rechners**, ohne dass sich jemand
  anmeldet.
- Er läuft weiter, wenn der Rechner **gesperrt** wird (Win+L), sich jemand
  **abmeldet**, ein **anderer Benutzer** sich anmeldet oder ein neuer Benutzer
  angelegt wird – er hängt an keiner Anmeldung.
- Windows startet ihn nach einem Absturz **selbst neu**.
- Verbindungen, die abreißen, baut er **eigenständig wieder auf**.
- Er schreibt mit, was passiert – `gateway.log` neben der Programmdatei.

### 3.4 Prüfen, ohne dass etwas läutet

Dieselbe Datei beantwortet alle Fragen zum Betrieb:

| Menü | Befehl | Wofür |
|---|---|---|
| 2 | `--einstellungen` | Zugang, Simulation, Ruhezeit, E-Mail, Gerät, Zertifikat |
| 3 | `--status` | Läuft der Dienst? Was steht zuletzt im Protokoll? |
| 4 | `--testlauf` | Läuft sichtbar im Fenster und löst **nichts** aus |
| 5 | `--diagnose` | Prüft die verschlüsselte Verbindung zum Broker |
| 6 | `--neustart` | Anhalten und wieder starten |
| 7 | `--anhalten` | Anhalten, um die Programmdatei ersetzen zu können |
| 8 | `--entfernen` | Dienst wieder abmelden |

Zeigt der **Testlauf** die richtigen Auslösungen, ist alles richtig verdrahtet.
In ChurchTools steht dann unter **Ereignis-Log**, wann der Dienst gestartet ist
und ob er verbunden war.

Zum Scharfschalten: Menüpunkt **2 → 2** und bei „Simulation einschalten?" **n**
antworten. Der Dienst wird danach von selbst neu gestartet, damit die Änderung
gilt.

### Alles, was sich einstellen lässt

Menüpunkt **2** zeigt zuerst, was gerade gilt, und führt dann durch die
einzelnen Punkte:

| Punkt | Wofür | Wenn nichts eingestellt ist |
|---|---|---|
| Zugang zu ChurchTools | Adresse und Login-Token | – (wird gebraucht) |
| Simulation | löst der Dienst wirklich aus? | ein: es wird nichts ausgelöst |
| Ruhezeit | z. B. `22:00-06:00` – darin wird **nie** ausgelöst | keine |
| E-Mail-Versand | Postausgang für Störungsmeldungen, auf Wunsch mit Testmail | aus, es bleibt beim Protokoll |
| Gerät | Seriennummer und Gerätepasswort | werden aus der Erweiterung gelesen |
| Zertifikatsbündel | nur bei Virenscanner oder Firmen-Firewall nötig | die Zertifikate des Systems |

Die Datei `.env` muss dafür nie geöffnet werden – das Programm schreibt sie,
mit Kommentaren, und lässt eigene Zusätze darin unangetastet. Die Eingabetaste
behält den gezeigten Wert, ein **Minus** (`-`) löscht ihn.

> Die **E-Mail-Zugangsdaten** werden bevorzugt in der Erweiterung gepflegt
> (Untermenü „E-Mail-Versand"); der Gateway liest sie von dort. Hier einzutragen
> sind sie nur, wenn das nicht möglich ist.

> Wer den Gateway vorher in der **Aufgabenplanung** hatte: Beim Einrichten
> werden solche Einträge gesucht und abgeschaltet. Sonst liefe er doppelt – und
> es würde zweimal geläutet.

### 3.5 Aktualisierungen kommen von selbst

Der Dienst sieht alle sechs Stunden nach, ob es eine neue Fassung gibt, und
spielt sie ein – aber nur, wenn sie **ihn** betrifft und wenn gerade **nichts
läutet** (und in der nächsten halben Stunde nichts ansteht). Der Neustart
dauert Sekunden und erscheint im Ereignis-Log als Information, nicht als
Störung. Meldet er sich danach binnen zehn Minuten nicht zurück, gilt das als
Ausfall – dann kommt die übliche Meldung samt E-Mail.

Die bisherige Programmdatei bleibt als `.alt` liegen, bis die neue läuft.

Abschalten: **Einstellungen → 7**. Dann gilt der Weg von Hand:

### 3.6 Von Hand auf eine neue Version wechseln

Die Einrichtung ist einmalig. Bei einer neuen Fassung bleibt alles stehen, was
schon da ist – Zugangsdaten, bereits ausgelöste Termine und das Protokoll:

1. Programmdatei starten → **7 (Dienst anhalten)**. Windows sperrt die Datei
   eines laufenden Dienstes; ohne diesen Schritt lässt sie sich nicht ersetzen
   („Zugriff verweigert").
2. Die neue `Glockensteuerung-Gateway.exe` über die alte kopieren.
3. Neue Datei starten → **1**. Sie meldet, was sie vorgefunden hat
   („Vorhandene Einrichtung gefunden … Nichts davon wird überschrieben"),
   trägt den Dienst auf die neue Datei ein und startet ihn.

Wer die neue Datei lieber **daneben** legt (anderer Name oder Ordner): Schritt 1
entfällt, aber **3** ist dann Pflicht – sonst startet Windows weiter die alte
Fassung. Ob das passiert ist, sagt `--status`: Dort steht eine Warnung, wenn der
Dienst eine andere Datei benutzt als die gerade gestartete.

### 3.7 Linux (oder eigener Python-Betrieb)

Der Quelltext steckt in „Source code" des
[neuesten Releases](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest)
– oder direkt aus Git:

```bash
git clone https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung.git
cd Glockensteuerung/gateway

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python dienst.py --einrichten     # fragt Adresse und Token ab, schreibt .env
python scheduler.py --dry-run     # plant aus euren Terminen, löst NICHT aus
```

Für den Dauerbetrieb eine systemd-Unit,
`/etc/systemd/system/voco-gateway.service`:

```ini
[Unit]
Description=VOCO Glocken-Gateway
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/pfad/zu/gateway
ExecStart=/pfad/zu/gateway/.venv/bin/python scheduler.py
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

### 3.8 Ruhezeit & Sicherheit (empfohlen)

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
| „Automatik nicht erreichbar" in der Extension | Der Gateway meldet sich nicht mehr. Unter Windows: `Glockensteuerung-Gateway.exe --status` – dort steht, ob der Dienst läuft und was zuletzt im Protokoll stand. |
| Der Dienst lief, tat aber nichts | Bis Version 26.7 beendete er sich stillschweigend, sobald die ChurchTools-Sitzung ablief oder beim Hochfahren noch kein Netz da war. Ab 26.8 meldet er sich selbst neu an und versucht es weiter – die neue Fassung installieren. |
| Es läutet doppelt | Es läuft noch ein zweiter Gateway, meist ein alter Eintrag in der Aufgabenplanung. `--status` nennt solche Einträge; `--installieren` schaltet sie ab. Seit 26.10 zieht sich ein zweiter Gateway von selbst zurück und schreibt den Grund ins Protokoll. |
| Zeitweise wird gar nicht geläutet | Der Rechner geht schlafen – währenddessen läuft der Dienst nicht. `--status` weist darauf hin; abschalten beim Einrichten oder in den Energieoptionen („Energiesparmodus: Niemals"). |
| Windows meldet „Der Computer wurde durch Windows geschützt" | Die Programmdatei ist nicht signiert. *Weitere Informationen → Trotzdem ausführen*. |
| Keine Programme in der Liste | Am Gerät sind (noch) keine **Sofort-PGS** angelegt. |
| Der Testlauf (`--testlauf`, Menüpunkt 4) zeigt keine Auslösungen | Der Gateway schreibt den Grund ins Log: keine Termine im Zeitraum, oder kein Titel passt exakt (er nennt dann Gesuchtes **und** Vorhandenes). Danach Schreibweise bzw. Kalender der Regel korrigieren. |
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
