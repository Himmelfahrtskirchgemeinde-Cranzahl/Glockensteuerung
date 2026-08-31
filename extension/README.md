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

- **Ohne eigene Software:** GitHub baut die ZIP – Repo-Tab **Actions** → Workflow
  „ChurchTools-Extension bauen (ZIP)" → **Run workflow**; ZIP unter *Artifacts*.
  Bei einem Versions-Tag (`v*`) hängt sie zusätzlich am **Release**. Details:
  [`../ANLEITUNG.md`](../ANLEITUNG.md), Teil 1.
- **Lokal:** siehe „Bauen & Installieren" unten.
- (#bauen--installieren)

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

- **Status:** Gerät online?, Liste der startbaren Sofort-PGS.
- **Manuell auslösen/stoppen** (mit Sicherheitsabfrage – löst echtes Läuten aus).
- **Gerät konfigurieren:** Seriennummer, Geräte-Passwort, Broker-URL.
- **Automatik-Regeln:** je Regel Kalender und/oder Veranstaltungsart → PGS +
  Vorlaufzeit. Gespeichert im ChurchTools-KV-Store (`custommodules`).

## 🔐 Sicherheit

Seriennummer + Geräte-Passwort erlauben das Läuten. Sie liegen im ChurchTools-
KV-Store; der Zugriff auf dieses Modul sollte auf Berechtigte beschränkt werden.
Die Verbindung zum HEW-Broker läuft direkt aus dem Browser per MQTT-over-WSS
(wie die offizielle HEW-Web-App).

## Technik

- Frontend: TypeScript + Vite (kein Framework, wie die Boilerplate).
- MQTT: `mqtt` (MQTT.js) über WebSocket — Protokoll siehe
  [`../docs/VOCO-MQTT-Protokoll.md`](../docs/VOCO-MQTT-Protokoll.md).
- ChurchTools-API: `@churchtools/churchtools-client`.
