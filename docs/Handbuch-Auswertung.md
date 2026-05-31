# Handbuch-Auswertung VOCO-futura ST5

Ziel: aus der **offiziellen Bedienungsanleitung** klären, **wie** sich die ST5
ansteuern lässt (lokal vs. Cloud, App-Verbindung, Programmauswahl) — als
verlässliche Grundlage statt Raten per Netzwerk-Scan.

**Quelle:** `https://hew-voco.de/downloads/Bedienungsanleitung VOCO - futura ST5.pdf`

> ⚠️ Aus der Cloud-Umgebung ist das PDF **nicht abrufbar** (403). Damit ich es
> **vollständig** auswerten kann, bitte das **PDF ins Repo hochladen**
> (GitHub → „Add file" → „Upload files", z. B. nach `docs/manual/`).
> Alternativ: Fotos/Screenshots der relevanten Seiten hier teilen.

---

## Worauf es ankommt (gezielte Suchbegriffe im PDF)

Bitte die Kapitel zu diesen Themen ansehen (oder mich, sobald das PDF da ist):

1. **Netzwerk / LAN / WLAN / IP** — wie wird das Gerät ins Netz gebracht, feste IP?
2. **App / VOCO-futura / Verbindung** — verbindet die App sich **direkt mit dem
   Gerät im LAN** oder über ein **Konto/Portal (Cloud)**?
3. **Konto / Registrierung / Portal / `hew-voco.de`** — braucht man ein
   Online-Konto? (= starker Cloud-Hinweis)
4. **Programm / Läuteprogramm / PGS / Sofort-PGS** — wie heißen Programme, wie
   werden sie ausgewählt/gestartet? Gibt es Nummern/IDs?
5. **Schnittstelle / API / Steuereingänge / Klemmen / potentialfrei** — gibt es
   eine externe Auslösemöglichkeit (Eingänge) als Alternative zur App?
6. **Fernsteuerung / Fernzugriff** — wie genau funktioniert „Steuern von unterwegs"?

---

## Was ich daraus ableite

- **Lokal** (App ↔ Gerät im LAN): Anbindung über Gateway im selben Netz möglich.
- **Cloud** (App ↔ HEW-Portal): Anbindung nur über HEW-Cloud/API oder per
  Steuereingängen; siehe [`HEW-Cloud-API.md`](HEW-Cloud-API.md) und
  [`HEW-Rueckfragen.md`](HEW-Rueckfragen.md).
- **Steuereingänge vorhanden:** robuste, herstellerunabhängige Alternative
  (Gateway + Relais), unabhängig von App/Cloud.

→ Ergebnis trage ich anschließend in [`Analyse-Befunde.md`](Analyse-Befunde.md)
und [`Konzept.md`](Konzept.md) ein und lege den finalen Umsetzungsweg fest.
