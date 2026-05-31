# HEW VOCO Cloud-Portal (app.hew-voco.de) — HYPOTHESE, zu prüfen

> ⚠️ **Status: unbestätigt.** Belegt ist nur, dass **`hew-voco.de/login` /
> `app.hew-voco.de`** ein **Web-Portal mit Anmeldung** ist (aus Websuche).
> **Nicht** belegt ist, ob es dort eine API/API-Keys gibt. (Eine frühere Notiz
> hatte das fälschlich als gesichert dargestellt — hiermit korrigiert.)
> Aus der Cloud-Umgebung ist das Portal nicht erreichbar (403).

## Warum diese Spur wichtig ist

HEW bewirbt die VOCO-futura mit Fernsteuerung *„von zu Hause, unterwegs oder aus
dem Büro"* und einem **LAN-Modul**. Zusammen mit dem Login-Portal spricht das
dafür, dass die App **möglicherweise über die HEW-Cloud** steuert (statt rein
lokal). Das würde auch erklären, warum lokal **kein** ansteuerbarer Port
gefunden wurde. **Bewiesen ist das aber nicht.**

## Was zu klären ist (sobald du im Portal bist)

1. Gibt es im eingeloggten Portal einen Bereich **„API", „Integrationen",
   „Entwickler", „Webhooks", „Token/Schlüssel"**? → Screenshot.
2. Falls ja: Basis-URL, Auth-Verfahren, Endpunkte zum **Programme auflisten** und
   **Programm starten**. (Dann ist das der sauberste Weg, ganz ohne Reverse-Eng.)
3. Falls nein: Steuerung läuft evtl. nur über App/Cloud ohne offene API →
   dann ist die **HEW-Anfrage** ([`HEW-Rueckfragen.md`](HEW-Rueckfragen.md)) der Weg.

## Sicherheit (falls doch API-Keys existieren)

- API-Key/Token ist ein **Geheimnis** → **nie** ins Repo/Chat, in Screenshots
  unkenntlich machen. Lokal in `.env` (per `.gitignore` ausgeschlossen),
  Vorlage: [`../.env.example`](../.env.example).
