# HEW VOCO Web-Portal (www.hew-voco.de) — belegte Fakten

## Was das Handbuch sagt (Kap. 4.7 „Netzwerk", Kap. „Speicherkarte/Backup")

- Die VOCO-futura ST5 kann per **LAN (RJ45)** oder **WLAN (optional)** ins Netz.
  Internet dient für **Zeit-Sync** *und* **Fernsteuerung\* per Browser**.
- **Fernsteuerung/Konfiguration läuft über `www.hew-voco.de`** (Benutzerkonto,
  „hier registrieren"). Kostenloses Testen möglich.
- **\* Voller Funktionsumfang nur mit kostenpflichtigem Freischaltcode**
  (Vertriebspartner / `0 52 21 / 59 04-21`, `kirchentechnik@hew-hf.de`).
  Ohne Freischaltcode u. a. **kein Download** von Konfigurationen.
- **Backups** lassen sich auf `hew-voco.de` **hochladen und bearbeiten**
  (ebenfalls Freischaltcode nötig).
- „**Fernzugriff erlauben**" (Einstellungen→Sicherheit) = Fernwartung, braucht
  Internet.

## Bewertung

- Es gibt also ein **offizielles Web-Portal mit Fernsteuerung** – das ist die
  dokumentierte Cloud-Steuerung. Das erklärt, warum **lokal kein offener
  Steuer-Port** zu finden war.
- ⚠️ **Eine offene/dokumentierte Programmier-API ist im Handbuch NICHT erwähnt.**
  „Fernsteuerung per Browser" heißt nicht zwangsläufig „nutzbare API für
  Drittsysteme". Ob es eine API/Webhooks gibt, ist **offen** und am besten
  **direkt bei HEW** zu erfragen (siehe [`HEW-Rueckfragen.md`](HEW-Rueckfragen.md)).

## Falls eine API existiert (zu prüfen, optionaler Weg)

> Nur relevant, wenn HEW eine API bestätigt **oder** du im eingeloggten Portal
> API-Aufrufe siehst. **Aktuell nicht der gewählte Hauptweg** (das ist Variante A).

1. Im Portal einloggen, **F12 → Network → Fetch/XHR**, lesende Aktion ausführen,
   einen Aufruf inspizieren: **URL-Muster, Methode, Auth-Header-Name** (nicht den
   Wert!), Antwort-JSON.
2. Erkenntnisse hier eintragen.

### 🔐 Sicherheit
- Zugangsdaten / Tokens / API-Keys sind **Geheimnisse**: **nie** in Repo, Chat,
  Screenshots oder Shell-History. Lokal nur in **`.env`** (per `.gitignore`
  ausgeschlossen), Vorlage [`../.env.example`](../.env.example).
- Aus dieser Auswertungsumgebung werden **keine** Zugangsdaten an externe Hosts
  gesendet; API-Tests laufen lokal beim Nutzer.
