# ChurchTools-Extension „Glockensteuerung"

Custom-Module für ChurchTools: Statusanzeige, manuelles Auslösen/Stoppen der
VOCO-Läuteprogramme und Pflege der **Automatik-Regeln** (Termin → Programm).
Die Regeln werden vom [Gateway-Dienst](../gateway/README.md) für das
automatische Läuten genutzt.

Basiert auf dem offiziellen
[ChurchTools extension-boilerplate](https://github.com/churchtools/extension-boilerplate).

> **📖 Komplette Einrichtung Schritt für Schritt: [`../ANLEITUNG.md`](../ANLEITUNG.md)**

> **🛡️ Simulationsmodus:** Das Modul startet immer in Simulation – „Läuten"
> sendet dann **nichts**, sondern zeigt im Ereignis-Log nur, was passieren würde
> (und die echten Antworten der Anlage). Erst nach bewusstem Ausschalten des
> Schalters wird real geläutet.

> **📟 Kompatibilität:** Aktuell werden nur **HEW VOCO-futura**-Geräte unterstützt
> (z. B. ST5, mit LAN/WLAN-Modul und `hew-voco.de`-Portal). Weitere HEW-Systeme und
> andere Hersteller folgen; eine **universelle** Lösung ist später geplant.

## ZIP für ChurchTools bekommen

- **Empfohlen – fester Link:** [`glockensteuerung.zip`](https://github.com/Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung/releases/latest/download/glockensteuerung.zip)
  aus dem neuesten Release. Der Dateiname enthält **keine** Version, deshalb
  bleibt der Link dauerhaft gültig. Herunterladen und **unverändert** hochladen.
- **Bestimmte Version:** Jede Version hat ein eigenes Release mit ihrem
  Changelog. Die Datei heißt dort ebenfalls `glockensteuerung.zip` – welche
  Version darin steckt, sagt der Titel des Release („Version 26.8.0").
- **Actions-Artifact:** Repo-Tab **Actions** → Workflow „Erweiterung und Gateway
  bauen (ZIP)" → **Run workflow**; Ergebnis unter *Artifacts*.
  > ⚠️ **Wichtig:** GitHub verpackt jedes Artifact **noch einmal** in eine ZIP →
  > du lädst also eine **ZIP-in-ZIP** herunter. Lade **nicht** diese äußere Datei
  > hoch (sonst `ccm.files.zip.missing.index.html`), sondern **entpacke sie
  > einmal**. Darin liegen die innere `glockensteuerung-v….zip` für ChurchTools
  > **und** `Glockensteuerung-Gateway.exe` für den Gateway-Rechner. **Nicht**
  > per Finder neu komprimieren (das erzeugt `__MACOSX/` → Upload-Fehler).
- **Lokal:** siehe „Bauen & Installieren" unten (erzeugt direkt die richtige ZIP
  in `releases/`).

Details: [`../ANLEITUNG.md`](../ANLEITUNG.md), Teil 1.

## Entwicklung

```bash
cd extension
npm install
cp .env-example .env      # VITE_KEY + (für dev) VITE_BASE_URL/USERNAME/PASSWORD
npm run dev
```

> Für `npm run dev` in der ChurchTools-Instanz CORS erlauben:
> System-Einstellungen → Integrationen → API → CORS → Origin `http://localhost:5173`.

## Bauen & Installieren

```bash
npm run deploy            # baut + packt ZIP nach releases/
```

Dann in ChurchTools: **Admin → Erweiterungen → hochladen** und das ZIP installieren.
Der Modul-Key (`VITE_KEY`, Standard `glockensteuerung`) muss zu dem passen, was
der Gateway erwartet (`VOCO_EXT_KEY`).

## Funktionen

- **Status:** Gerät online?, läuft die Automatik?, Liste der startbaren
  Sofort-PGS, Vorschau der nächsten Läutungen.
- **Manuell auslösen/stoppen** (mit Sicherheitsabfrage – löst echtes Läuten aus).
- **Gerät konfigurieren:** Seriennummer, Geräte-Passwort, Broker-URL.
- **Automatik-Regeln:** je Regel Kalender und/oder Termin-Titel (exakter
  Vergleich) → PGS + Vorlaufzeit. Gespeichert im ChurchTools-KV-Store
  (`custommodules`).
- **Ereignis-Log:** dauerhaft in ChurchTools, wochenweise abgelegt (acht Wochen).
  Mit Volltextsuche, Filtern nach Art, Schnellfilter „Nur Auffälliges" und
  Zeitraum; Störungen sind rot, Hinweise gelb. Herunterladen speichert die
  aktuelle Auswahl als Textdatei.

## 🔐 Sicherheit & Berechtigungen

Seriennummer + Geräte-Passwort erlauben das Läuten. Sie liegen im ChurchTools-
KV-Store; der Zugriff auf dieses Modul sollte auf Berechtigte beschränkt werden.
Die Verbindung zum HEW-Broker läuft direkt aus dem Browser per MQTT-over-WSS
(wie die offizielle HEW-Web-App).

> **Schritt für Schritt, mit Rollenvorschlägen:**
> [`../ANLEITUNG.md`, Teil 4](../ANLEITUNG.md#teil-4--wer-darf-was-rechte-in-churchtools)

Die Extension nutzt die **vorhandenen ChurchTools-Rechte** des Custom-Modules –
und zwar **pro Untermenü**. Jedes Untermenü ist eine eigene **Kategorie**, deren
Rechte ein Admin in der Rechteverwaltung (→ „Glockensteuerung") einzeln vergibt:

| Untermenü (= Kategorie, `shorty`) | „…sehen" (view custom data) | „…bearbeiten" (edit/create custom data) |
|---|---|---|
| **Steuerung** (`steuerung`) | Untermenü sichtbar + **Läuten/Testen**, Gerät und Lebenszeichen lesen | Seriennummer/Passwort ändern |
| **Ereignis-Log** (`ereignislog`) | Log sichtbar | – |
| **Automatik-Regeln** (`regeln`) | Regeln ansehen | Regeln anlegen/ändern/löschen |
| **E-Mail-Versand** (`email`) | Postausgang ansehen | Zugangsdaten ändern |

> Die **Gerätedaten liegen bewusst in „Steuerung"** und nicht in einer eigenen
> Kategorie: Wer läuten darf, muss die Verbindungsdaten lesen können – sonst
> sähe er das Gerät als „nicht eingerichtet". Die Kategorie **`email`** enthält
> dagegen das Postausgangs-Passwort und sollte **nicht** für alle lesbar sein.

**Sicherheitsmodus (Scharfschalten):** Den Simulationsmodus **deaktivieren** –
und damit echtes Läuten freischalten – darf **nur**, wer die ChurchTools-
Berechtigung **„Erweiterung verwalten"** (`administer custom modules`) hat. Für
alle anderen ist der Schalter gar nicht sichtbar; sie können nur im
Simulationsmodus „Testen".

„Hilfe/Feedback" ist immer für alle da. Admins mit „administer custom modules"
dürfen alles. Wer ein Untermenü nur „sehen" darf, bekommt es **schreibgeschützt**;
ohne „sehen" ist das Untermenü ausgeblendet. Die UI blendet nur passend aus –
**erzwungen werden die Rechte serverseitig** von ChurchTools auf den
KV-Endpunkten. Die vier Kategorien werden beim ersten Öffnen durch eine
berechtigte Person (Admin) automatisch angelegt – vorher kann der Gateway sie
nicht lesen und meldet, dass die Extension noch nie geöffnet wurde.

## Technik

- Frontend: **Vue 3** (`<script setup>`) + TypeScript + Vite. Die Oberfläche
  steckt in einer einzigen `App.vue`; das Design kommt aus `app.css`
  (eigene `.gs-`-Klassen, kein CSS-Framework).
- **Hell und dunkel**: `utils/thema.ts` erkennt das Thema von ChurchTools und
  setzt `data-thema="hell|dunkel"` am `<html>`; `app.css` hängt daran eine
  zweite Farbbelegung derselben Variablen – Aufbau und Abstände bleiben
  gleich. Erkannt wird an der **gemessenen Farbe der Fläche**, auf der das
  Modul liegt (im iframe: die Umgebung des Rahmens), ersatzweise an üblichen
  Kennzeichen wie `data-theme` und zuletzt an der Einstellung des Rechners.
  Ein `MutationObserver` zieht nach, wenn ChurchTools umgeschaltet wird.
  ⚠ `html` und `body` dürfen deshalb **nicht** eingefärbt werden – sonst
  mäße die Erkennung die eigene Farbe. Die Fläche trägt `.gs`.
- MQTT: `mqtt` (MQTT.js) über WebSocket — Protokoll siehe
  [`../docs/VOCO-MQTT-Protokoll.md`](../docs/VOCO-MQTT-Protokoll.md).
- ChurchTools-API: `@churchtools/churchtools-client`.
