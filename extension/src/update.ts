/**
 * Prüft, ob eine neuere Fassung der Extension veröffentlicht wurde.
 *
 * Das Repository ist öffentlich, deshalb kann der Browser die GitHub-API direkt
 * fragen (CORS ist erlaubt). **Ohne Token** – das Bundle ist für jeden lesbar,
 * der das Modul öffnet, ein Zugangsschlüssel darin wäre öffentlich.
 *
 * Unauthentifiziert erlaubt GitHub nur 60 Abfragen pro Stunde und IP. Bei einer
 * Gemeinde hinter einem gemeinsamen Anschluss teilen sich das ALLE Benutzer.
 * Deshalb zwei Sparmaßnahmen:
 *  - Gefragt wird nur, wer die Extension auch aktualisieren kann (Recht
 *    „Erweiterung verwalten") – für alle anderen wäre der Hinweis ohnehin nutzlos.
 *  - Das Ergebnis liegt im ChurchTools-KV-Store und gilt einen Tag. Eine Abfrage
 *    reicht damit für die ganze Gemeinde.
 *
 * `/releases/latest` überspringt Prereleases. Das rollierende „latest"-Release
 * (der feste Download-Link) ist bewusst als Prerelease angelegt und wird hier
 * deshalb NICHT geliefert – zurück kommt das Gruppen-Release, dessen Tag genau
 * die neueste Version trägt.
 */

const REPO = 'Himmelfahrtskirchgemeinde-Cranzahl/Glockensteuerung';
const RELEASES_API = `https://api.github.com/repos/${REPO}/releases/latest`;

/** Fester Download-Link – ändert sich nie (siehe .github/workflows). */
export const DOWNLOAD_URL = `https://github.com/${REPO}/releases/download/latest/glockensteuerung.zip`;

/** Wie lange ein geholtes Ergebnis gilt: ein Tag. */
export const CHECK_MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Im KV-Store abgelegtes Ergebnis der letzten Prüfung. */
export interface UpdateCheck {
    /** Neueste veröffentlichte Version ohne „v", z. B. „26.5.7". */
    latest: string;
    /** Wann zuletzt bei GitHub gefragt wurde (ISO-Zeitstempel). */
    at: string;
}

/**
 * „26.5.7" oder „26.5.7-3-gabc123" -> [26, 5, 7]. Alles Unbrauchbare -> null.
 *
 * Der Zusatz nach der Versionsnummer entsteht bei Ständen ZWISCHEN zwei Tags
 * (`git describe`). Er wird bewusst abgeschnitten: Ein solcher Stand ist neuer
 * als der Tag, nie älter – die drei Zahlen genügen also für den Vergleich.
 */
function parts(v: string): [number, number, number] | null {
    const m = /^(\d+)\.(\d+)\.(\d+)/.exec(String(v ?? '').trim().replace(/^v/, ''));
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

/**
 * Ist `latest` neuer als `current`?
 *
 * Zahlenweise vergleichen, nicht als Text: „26.10.0" ist neuer als „26.9.9",
 * alphabetisch wäre es umgekehrt. Lässt sich eine der beiden Angaben nicht
 * lesen, gilt „nicht neuer" – lieber kein Hinweis als ein falscher.
 */
export function isNewer(latest: string, current: string): boolean {
    const a = parts(latest);
    const b = parts(current);
    if (!a || !b) return false;
    for (let i = 0; i < 3; i++) {
        if (a[i] !== b[i]) return a[i] > b[i];
    }
    return false;
}

/** Gilt das gespeicherte Ergebnis noch? */
export function isFresh(check: UpdateCheck | null, now: number = Date.now()): boolean {
    if (!check?.at) return false;
    const t = new Date(check.at).getTime();
    if (!Number.isFinite(t)) return false;
    // Auch ein Zeitstempel aus der Zukunft (falsch gestellte Uhr) gilt als frisch,
    // sonst würde bei jedem Aufruf neu gefragt.
    return Math.abs(now - t) < CHECK_MAX_AGE_MS;
}

/**
 * Neueste veröffentlichte Version bei GitHub erfragen.
 * Gibt null zurück, wenn das nicht klappt – die Prüfung ist Beiwerk und darf
 * die Bedienung nie stören (kein Netz, Rate-Limit, Repo umbenannt).
 */
export async function fetchLatest(): Promise<UpdateCheck | null> {
    try {
        const res = await fetch(RELEASES_API, {
            headers: { Accept: 'application/vnd.github+json' },
        });
        if (!res.ok) return null;
        const j = (await res.json()) as { tag_name?: string };
        const latest = String(j?.tag_name ?? '').trim().replace(/^v/, '');
        return parts(latest) ? { latest, at: new Date().toISOString() } : null;
    } catch {
        return null;
    }
}
