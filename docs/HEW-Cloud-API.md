# HEW VOCO Cloud-API (app.hew-voco.de) — der saubere Weg ✅

**Durchbruch (2026-05-31):** Im Web-Portal **`app.hew-voco.de`** lassen sich unter
**Einstellungen → API** **API-Keys generieren**. Es gibt also eine **offizielle,
unterstützte Cloud-API**. Damit ist Reverse-Engineering (Wireshark/Portscan)
**hinfällig** — wir nutzen die dokumentierte Schnittstelle.

> **Hinweis:** Aus der Cloud-Entwicklungsumgebung ist `app.hew-voco.de` nicht
> erreichbar (403). Die API-Aufrufe erfolgen ohnehin vom **Gateway-PC vor Ort**.

---

## 🔐 Sicherheit des API-Keys (wichtig!)

- Der API-Key ist ein **Geheimnis** (Zugriff auf die Glockensteuerung!).
- **Niemals** in dieses Repository committen, **nicht** in den Chat schreiben,
  **nicht** in Screenshots zeigen (unkenntlich machen).
- Ablage später lokal in einer **`.env`**-Datei (ist via `.gitignore` ausgeschlossen),
  Vorlage: [`../.env.example`](../.env.example).
- Falls ein Key versehentlich öffentlich wurde: im Portal **widerrufen** und neu
  erzeugen.

---

## Was ich aus dem Portal brauche (Screenshots/Notizen)

Bitte ohne den geheimen Key offenzulegen:

1. **API-Dokumentation:** Gibt es bei „Einstellungen → API" einen Link wie
   *„Dokumentation", „API Docs", „Swagger", „Hilfe"*? → Screenshot / URL.
   - Häufige Adressen zum Ausprobieren (im Browser, eingeloggt):
     `app.hew-voco.de/api`, `/api/docs`, `/api/v1`, `/swagger`, `/docs`,
     `/api/documentation`.
2. **Basis-URL & Version** der API (z. B. `https://app.hew-voco.de/api/v1/...`).
3. **Auth-Verfahren:** Wie wird der Key mitgegeben? (Meist HTTP-Header
   `Authorization: Bearer <KEY>` oder `X-API-Key: <KEY>`.) Steht das in der Doku?
4. **Endpunkte** für:
   - **Steuerungen/Anlagen auflisten** (welche Geräte hängen am Konto?),
   - **Programme auflisten** (Namen + IDs der Läuteprogramme),
   - **Programm starten/auslösen** (welcher Endpunkt, welche Parameter?).
5. **Programmliste:** Screenshot der in eurer Anlage vorhandenen Programme
   (Name + ggf. Nummer/ID).

> Wenn es eine Doku-Seite gibt: ein, zwei Screenshots der Endpunkt-Liste genügen
> mir, um den Client zu schreiben.

---

## Geplante Architektur mit Cloud-API

```
ChurchTools (Events) ──► Gateway-PC (vor Ort) ──HTTPS+API-Key──► app.hew-voco.de ──► ST5
```

1. Gateway liest ChurchTools-Termine (Veranstaltungsmodul).
2. Mapping Veranstaltungsart → VOCO-Programm (ID aus der API).
3. Zur richtigen Zeit ruft das Gateway den **„Programm starten"-Endpunkt** der
   HEW-Cloud-API auf.

Vorteile: offiziell unterstützt, kein Eingriff in die Anlage, übersteht
Firmware-Updates, kein Verkabeln.

---

## Nächste Schritte

1. API-Key generieren (geheim halten).
2. API-Doku/Endpunkte aus dem Portal beschaffen (s. o.).
3. Damit: kleinen Cloud-API-Client schreiben (zuerst **nur lesend**: Anlagen/
   Programme auflisten), lokal testen.
4. Danach: ChurchTools-Anbindung + Mapping + Zeitsteuerung.
