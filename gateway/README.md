# Gateway-Dienst (Automatisches Läuten)

Liest die ChurchTools-Termine + die in der Extension konfigurierten Regeln und
löst zur richtigen Zeit das passende VOCO-Läuteprogramm per MQTT aus.

Läuft auf **irgendeinem dauerhaft laufenden Rechner mit Internet** – das muss
**nicht** in der Kirche stehen: Raspberry Pi, kleiner Server/VPS oder ein
vorhandener Dauer-PC. (Steuerung und ChurchTools laufen über das Internet.)

> **📖 Komplette Einrichtung Schritt für Schritt: [`../ANLEITUNG.md`](../ANLEITUNG.md)**

> **🛡️ Simulation:** `Glockensteuerung-Gateway.exe --testlauf` bzw.
> `python scheduler.py --dry-run` plant und protokolliert,
> löst aber **nicht** aus. Dauerhaft: `VOCO_SIMULATION=1` in der `.env`.

## Einrichtung

**Windows:** gar nichts von Hand – die fertige Programmdatei fragt beim ersten
Start nach Adresse und Token und legt die `.env` selbst an (siehe
„Dauerbetrieb unter Windows" weiter unten).

**Linux / eigener Python-Betrieb:**

```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
python dienst.py --einstellungen  # fragt alles ab und schreibt die .env
```

Das Menü deckt alles ab, was in der `.env` stehen kann: Zugang, Simulation,
Ruhezeit, Postausgang (auf Wunsch mit Testmail), Gerät und ein eigenes
Zertifikatsbündel. Eigene Zusätze in der Datei bleiben dabei unangetastet.

Wer die `.env` lieber selbst schreibt: `cp .env.example .env` und ausfüllen
(`CT_BASE_URL`, `CT_LOGIN_TOKEN`).

`CT_LOGIN_TOKEN` = Login-Token eines (technischen) ChurchTools-Benutzers.

**Benoetigte Rechte:** Der Benutzer muss die Kategorien des Moduls
„Glockensteuerung" **lesen** duerfen (Geraet + Regeln) und in der Kategorie
`steuerung` zusaetzlich **schreiben** duerfen. Das Schreibrecht braucht nur das
Lebenszeichen (Heartbeat), das der Dienst alle 40 Sekunden hinterlegt, damit die
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

## Dauerbetrieb unter Windows (empfohlen)

Für den Rund-um-die-Uhr-Betrieb gibt es eine fertige Programmdatei:
**`Glockensteuerung-Gateway.exe`** aus dem
[neuesten Release](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest).
Sie braucht kein Python und keine virtuelle Umgebung.

1. Die EXE in einen eigenen Ordner legen. Liegt dort schon eine `.env`, bleibt
   sie unverändert und wird benutzt.
2. Doppelklick → **1 (Einrichten)**. Das Menü bleibt danach offen; erst **0**
   schließt es. Gibt es noch keine `.env`, fragt das
   Programm nach der ChurchTools-Adresse und dem Login-Token, probiert beides
   sofort aus und legt die Datei selbst an.
3. Die Windows-Abfrage nach Administratorrechten bestätigen – die braucht es
   für das Anlegen des Dienstes.

Beim Einrichten wird nach dem **Ordner** gefragt, in dem die Datei dauerhaft
liegen soll – dieser Pfad landet im Dienst. Liegt sie im Download-, Desktop-
oder Temp-Ordner, schlägt das Programm `C:\Glockensteuerung` vor und nimmt
`.env` und `state.json` mit. Aus solchen Ordnern wird aufgeräumt; der Dienst
zeigte danach ins Leere und schwiege, ohne dass jemand einen Zusammenhang sieht.

Beim Installieren entsteht dabei alles, was gebraucht wird: der Ordner (falls
er noch nicht da ist), die Programmdatei darin, die `.env` mit den
Zugangsdaten, der Windows-Dienst – und eine Verknüpfung **„Glockensteuerung"**
im Startmenü, über die sich Einstellungen, Status und Protokoll später
jederzeit öffnen lassen.

Das war alles. Der Dienst steht danach in `services.msc` als
**Glockensteuerung Gateway** und

- startet beim Hochfahren des Rechners, **ohne dass sich jemand anmeldet**,
- wird von Windows nach einem Absturz selbst neu gestartet,
- baut Verbindungen, die abreißen, eigenständig wieder auf,
- schreibt mit, was passiert (`gateway.log` neben der EXE, umlaufend).

### Auf eine neue Version wechseln

Alles, was schon da ist, bleibt: Zugangsdaten, bereits ausgelöste Termine,
Protokoll. Der Ablauf: **7 (Dienst anhalten)** → neue Datei über die alte
kopieren → starten → **1**. Der Zwischenschritt ist nötig, weil Windows die
Datei eines laufenden Dienstes sperrt.

Beim Einrichten meldet das Programm, was es vorgefunden hat, und dass nichts
davon überschrieben wird. Zeigt der Dienst noch auf eine andere Programmdatei,
sagt `--status` das ausdrücklich – sonst liefe unbemerkt die alte Fassung weiter.

Weitere Schalter derselben Datei:

```text
Glockensteuerung-Gateway.exe --status         läuft er? was steht im Protokoll?
Glockensteuerung-Gateway.exe --einstellungen  Zugang, Simulation, Ruhezeit, E-Mail, Gerät
Glockensteuerung-Gateway.exe --neustart       anhalten und wieder starten
Glockensteuerung-Gateway.exe --anhalten       anhalten (um die Datei zu ersetzen)
Glockensteuerung-Gateway.exe --testlauf    läuft im Fenster, löst NICHTS aus
Glockensteuerung-Gateway.exe --diagnose    prüft die Zertifikatskette
Glockensteuerung-Gateway.exe --entfernen   Dienst wieder abmelden
```

Beim Einrichten werden **alte Einträge der Aufgabenplanung** gesucht, die
denselben Gateway starten, und abgeschaltet – sonst liefe er doppelt und es
würde zweimal geläutet.

> Beim ersten Start meldet sich Windows mit „Der Computer wurde durch Windows
> geschützt“. Das liegt daran, dass die Datei nicht mit einem gekauften
> Zertifikat signiert ist. Über *Weitere Informationen → Trotzdem ausführen*
> geht es weiter.

### Er hält sich selbst auf dem Stand

Eine Korrektur am Gateway nützt nichts, solange niemand an den Rechner der
Gemeinde geht. Der Dienst sieht deshalb alle sechs Stunden nach, ob es eine
neue Fassung gibt, und spielt sie selbst ein — **unter drei Bedingungen**:

1. **Nur, wenn es ihn betrifft.** Eine neue Fassung der Erweiterung ändert an
   diesem Programm nichts. Entschieden wird das am Changelog des Release: Steht
   dort ein Abschnitt „Gateway", ist etwas für ihn dabei.
2. **Nur, wenn nichts brennt.** Während geläutet wird oder eine halbe Stunde vor
   oder nach einer Auslösung wird nicht getauscht — ein Neustart dauert
   Sekunden, aber die falschen Sekunden wären die vor dem Gottesdienst.
3. **Der Weg zurück bleibt offen.** Die bisherige Programmdatei wird nicht
   gelöscht, sondern als `.alt` danebengelegt, bis die neue nachweislich läuft.

Was heruntergeladen wurde, wird vorher angesehen: Es muss von GitHub kommen,
mindestens 3 MB groß sein und mit der Kennung eines Windows-Programms beginnen.

Der Neustart löst **keine Störungsmeldung** aus: Der Dienst kündigt ihn im
Lebenszeichen an, und die Erweiterung weiß dadurch, dass Schweigen für die
nächsten zehn Minuten erwartet ist.

> **Wird der Dienst angehalten, hängt es davon ab, ob er wiederkommt.**
>
> | Auslöser | Meldung |
> |---|---|
> | **6 – Neustart** | keine: er ist Sekunden später wieder da |
> | **Selbstaktualisierung** | keine: derselbe Fall, nur mit neuer Fassung |
> | **7 – Anhalten** | **E-Mail** – er bleibt aus, bis ihn jemand startet |
> | **Windows** (Update, Herunterfahren, Virenscanner) | **E-Mail** |
>
> Verschickt wird sie vom Dienst **selbst**, bevor er geht.
>
> Das ist der einzige Augenblick, in dem das überhaupt geht: Die Meldung der
> Erweiterung liegt im Postausgang, bis der Dienst zurückkommt – **kommt er
> nicht zurück, kommt auch die Meldung nie**. Ein Browser kann kein SMTP
> sprechen; verschicken kann nur der Dienst.
>
> Was er nicht melden kann: einen Stromausfall oder einen abgestürzten
> Rechner. Dann ist er weg, bevor er etwas tun könnte. Wer auch das bemerken
> will, braucht einen Wächter außerhalb – etwa eine Überwachung, die den
> Rechner anpingt.

> **Im Ereignis-Log steht, welche Fassung läuft.** Jede Startmeldung nennt sie
> („Automatik-Dienst 26.10.0 gestartet …"), und hat sich der Dienst
> zwischendurch selbst aktualisiert, steht das als eigene Zeile davor:
> „Automatik-Dienst aktualisiert: 26.10.0 → 26.10.1." Ohne sie bliebe die
> Selbstaktualisierung völlig unsichtbar.

> Dasselbe gilt für den **Wiederanlauf** nach einer Störung. Reißt eine
> Verbindung ab, wartet der Dienst 15 Sekunden bis 5 Minuten und nimmt einen
> neuen Anlauf — gemeldet würde ein Ausfall aber schon nach zwei Minuten.
> Deshalb schreibt er vor dem Warten, bis wann er sich zurückmeldet; die
> Erweiterung zeigt in dieser Zeit **„Automatik verbindet neu"** und schlägt
> keinen Alarm. Kommt er danach nicht wieder, ist es ein Ausfall wie jeder
> andere. Meldet er sich danach nicht zurück, ist es
ein Ausfall wie jeder andere — mit E-Mail.

Abschalten lässt sich das über **Einstellungen → 7** (oder `VOCO_AUTO_UPDATE=0`).

### Was den Dienst nicht stört

Er läuft als `LocalSystem` und hängt an keiner Benutzersitzung:

| Vorgang | Dienst läuft weiter |
|---|---|
| Niemand angemeldet (nach dem Hochfahren) | ja |
| Abmelden, Benutzerwechsel, neuer Benutzer | ja |
| Rechner sperren (Win+L) | ja |
| Bildschirm aus | ja |
| **Energiesparmodus / Ruhezustand** | **nein** |

Die letzte Zeile ist die einzige echte Lücke: Ein schlafender Rechner läutet
nicht. Beim Einrichten wird deshalb geprüft, ob er im Netzbetrieb von selbst
schlafen geht, und angeboten, das abzuschalten (`powercfg`). `--status` weist
später erneut darauf hin, falls es doch eingeschaltet ist.

### Nur ein Gateway zur selben Zeit

Beim Start belegt der Dienst eine systemweite Sperre. Ein zweiter Gateway –
eine übriggebliebene Aufgabe in der Aufgabenplanung, ein von Hand gestartetes
`python scheduler.py`, ein zweites Fenster – zieht sich zurück und schreibt den
Grund ins Protokoll. Ohne das löst dasselbe Geläut zweimal aus, und das fällt
nicht im Protokoll auf, sondern im Dorf.

### Warum ein Dienst und keine Aufgabenplanung

Die Aufgabenplanung ist dafür gemacht, etwas zu einem Zeitpunkt zu **starten** –
nicht, etwas dauerhaft am Leben zu **halten**. Sie meldet „erfolgreich“, auch
wenn der Prozess Sekunden später gestorben ist, kennt ein Ausführungszeitlimit
und startet im Systemverzeichnis, wo keine `.env` liegt. Ein Dienst kennt diese
Fallen nicht.

## Dauerbetrieb unter Linux

```bash
python scheduler.py
```

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
- **Gibt nicht auf:** Fällt das Netz aus, läuft die ChurchTools-Sitzung ab oder
  ist beim Hochfahren noch keine Verbindung da, wartet der Dienst und versucht
  es erneut – statt sich zu beenden.
- **Plan bleibt stehen:** Ist ChurchTools vorübergehend nicht erreichbar, wird
  der zuletzt gelesene Plan weiter abgearbeitet. Ein Aussetzer der API lässt
  kein Geläut ausfallen.

## Dateien

| Datei | Zweck |
|---|---|
| `scheduler.py` | Hauptdienst (Planung + Auslösung, hält sich selbst am Leben) |
| `churchtools.py` | ChurchTools-API-Client (Kalender-Termine) |
| `config.py` | lädt Gerät + Regeln aus ChurchTools (oder .env) |
| `voco_mqtt.py` | MQTT-Client + CLI (`list`/`status`/`start`/`stop`) |
| `tls.py` | Wurzelzertifikate für MQTT und E-Mail |
| `diagnose.py` | prüft, warum eine verschlüsselte Verbindung scheitert |
| `dienst.py` | Bedienung: einrichten, Status, Protokoll (wird zur EXE gebaut) |
| `windienst.py` | meldet den Gateway als Windows-Dienst an |
| `pfade.py` | findet `.env`, Zustand und Protokoll neben dem Programm |
| `einrichtung.py` | Einstellungsmenü: fragt ab, prüft und schreibt die `.env` |
| `sperre.py` | verhindert, dass zwei Gateways gleichzeitig läuten |
| `aktualisierung.py` | holt neue Fassungen und tauscht die Programmdatei |
| `kv.py` | gemeinsamer Zugriff auf den Speicher der Extension |
| `heartbeat.py` | Lebenszeichen alle 40 Sekunden nach ChurchTools |
| `ereignisse.py` | hält Verbindungen und Ausfälle im Ereignis-Log fest |
| `outbox.py` | arbeitet den Postausgang der Extension ab |
| `notify.py` | verschickt Fehlermeldungen per E-Mail |

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

**Es fehlt das Zwischenzertifikat.** Genau das ist bei `hew-voco.de` der Fall,
und es ist der einzige, in dem im Browser alles funktioniert und nur das
Programm scheitert: Der Server sendet nur sein eigenes Zertifikat, nicht das der
ausstellenden Zwischenstelle. Browser holen das fehlende Stück selbstständig an
der Adresse nach, die im Zertifikat steht; Python tut das nicht.

**Der Dienst holt es jetzt selbst** — einmal, und legt es als
`zwischenzertifikat.pem` daneben. Beim nächsten Start reicht die Datei, es wird
nichts mehr geladen. Einzutragen ist dafür nichts. Nachgeladen wird nur bei
einem echten Zertifikatsfehler: Ein Netzproblem oder ein Port, der gar kein TLS
spricht, löst keinen Abruf aus.

**Aussteller ist eine öffentliche Stelle** (Let's Encrypt, DigiCert, Sectigo …):
Dann fehlen nur Wurzelzertifikate. Python bringt unter Windows keine mit. Der
Dienst nutzt deshalb das Bundle von `certifi`, das mit den Abhängigkeiten
installiert wird. Bleibt der Fehler:

```
pip install --upgrade certifi
```

> **Das gilt für jede Verbindung des Dienstes** – zur Anlage, zu ChurchTools,
> zum Postausgang und zur Aktualisierungsprüfung bei GitHub. Alle benutzen
> dieselben Quellen (Systemspeicher + `certifi` + ein eigenes Bundle).
>
> Die Aktualisierungsprüfung tat das bis Version 26.9.8.1 **nicht**: Sie fragte
> ohne diese Quellen bei GitHub nach und scheiterte auf Rechnern, deren
> Windows-Speicher die Wurzel nicht kennt – im Protokoll als
>
> ```
> Aktualisierungspruefung nicht moeglich: <urlopen error [SSL:
> CERTIFICATE_VERIFY_FAILED] ... unable to get local issuer certificate>
> ```
>
> Der Dienst lief dabei normal weiter und läutete; er blieb nur auf seiner
> Fassung stehen, weil er keine neue finden konnte.

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

