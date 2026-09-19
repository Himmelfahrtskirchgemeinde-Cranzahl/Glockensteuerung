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

/**
 * Fester Download-Link – ändert sich nie.
 *
 * `/releases/latest/download/<datei>` ist ein Weg, den GitHub selbst anbietet:
 * Er liefert immer die gleichnamige Datei des neuesten Releases. Jedes Release
 * trägt dafür neben der versionierten ZIP eine `glockensteuerung.zip` unter
 * festem Namen (siehe .github/scripts/release.sh).
 */
export const DOWNLOAD_URL = `https://github.com/${REPO}/releases/latest/download/glockensteuerung.zip`;

/** Übersicht aller Releases – Rückfallweg, wenn der Changelog nicht ladbar ist. */
export const RELEASES_URL = `https://github.com/${REPO}/releases`;

/** Wie lange ein geholtes Ergebnis gilt: ein Tag. */
export const CHECK_MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Im KV-Store abgelegtes Ergebnis der letzten Prüfung. */
export interface UpdateCheck {
    /** Neueste veröffentlichte Version ohne „v", z. B. „26.5.7". */
    latest: string;
    /** Wann zuletzt bei GitHub gefragt wurde (ISO-Zeitstempel). */
    at: string;
    /** Beschreibung des Releases – der Changelog. Fehlt bei alten Einträgen. */
    notes?: string;
}

/** Eine Zeile des aufbereiteten Changelogs (siehe `parseChangelog`). */
export type ChangelogZeile =
    | { art: 'version'; text: string }   // ## v26.5.6
    | { art: 'gruppe'; text: string }    // ### Verbesserungen
    | { art: 'bereich'; text: string }   // * **Steuerung**
    | { art: 'eintrag'; text: string }   //    * Der Satz
    | { art: 'text'; text: string };     // alles Übrige

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
 * Muss neu bei GitHub gefragt werden?
 *
 * Das Alter allein genügt nicht. Wird die Erweiterung aktualisiert, ist der
 * gespeicherte Stand sofort falsch – er nennt dann eine ältere Fassung als die
 * installierte und trägt deren Changelog. Bis er nach einem Tag verfällt, zeigt
 * das Fenster „Was ist neu" die Neuerungen einer Version, die längst installiert
 * ist. Genau das war zu sehen: Version 26.6.6 lief, das Fenster zeigte den
 * Changelog von 26.6.2.
 *
 * Eine installierte Fassung, die NEUER ist als die zuletzt gesehene
 * Veröffentlichung, kann es nicht geben – dieser Fall ist also ein sicheres
 * Zeichen, dass der Stand überholt ist.
 */
export function isStale(check: UpdateCheck | null, current: string,
                        now: number = Date.now()): boolean {
    if (!check?.notes) return true;
    if (!isFresh(check, now)) return true;
    return isNewer(current, check.latest);
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
        const j = (await res.json()) as { tag_name?: string; body?: string };
        const latest = String(j?.tag_name ?? '').trim().replace(/^v/, '');
        if (!parts(latest)) return null;
        return { latest, at: new Date().toISOString(), notes: String(j?.body ?? '') };
    } catch {
        return null;
    }
}

/**
 * Marken, die den Changelog in der Release-Beschreibung eingrenzen.
 *
 * Der Changelog steht dort seit 26.9 GANZ OBEN - er ist das Einzige, was sich
 * von Version zu Version ändert, und gehört deshalb zuerst gelesen. Alles
 * danach (welche Datei wofür da ist) ist bei jeder Fassung dieselbe Erklärung
 * und hat im Fenster „Was ist neu" nichts verloren.
 *
 * Ältere Veröffentlichungen haben es umgekehrt: erst die Erklärung, dann die
 * Startmarke, dann der Changelog. Beide Formen werden gelesen - sonst zeigte
 * das Fenster bei einem Blick zurück den falschen Ausschnitt.
 */
const ENDE_MARKER = '<!-- changelog-ende -->';
const MARKER = '<!-- changelog -->';

/**
 * Zerlegt die Release-Beschreibung in anzeigbare Zeilen.
 *
 * Bewusst ein eigener kleiner Parser statt einer Markdown-Bibliothek und ohne
 * `v-html`: Der Text stammt zwar aus dem eigenen Release, aber ungeprüftes HTML
 * in die Seite zu schreiben ist eine Tür, die man nicht aufmacht, wenn man sie
 * nicht braucht. Die Vorlage erzeugt ohnehin nur vier Formen (Version, Gruppe,
 * Bereich, Eintrag); alles andere wird als schlichter Text durchgereicht.
 */
/**
 * Überschrift des Abschnitts, der die Erweiterung betrifft.
 *
 * Die Release-Beschreibung führt beide Teile getrennt auf. Im Fenster „Was ist
 * neu" hat der Dienst nichts zu suchen: Wer hier liest, hat gerade die
 * Erweiterung in ChurchTools aktualisiert und kann mit „der Gateway startet
 * jetzt schneller" nichts anfangen.
 */
const TEIL_ERWEITERUNG = /^##\s+Erweiterung\b/im;

/** Überschrift des Abschnitts, der den Dienst betrifft. */
const TEIL_GATEWAY = /^##\s+Gateway\b/im;

/** Schneidet den Abschnitt der Erweiterung heraus, wenn es ihn gibt. */
function nurErweiterung(text: string): string {
    const treffer = TEIL_ERWEITERUNG.exec(text);
    if (!treffer) {
        // Steht dort nur ein Gateway-Teil, bringt diese Fassung für die
        // Erweiterung nichts Neues. Das gehört gesagt - sonst liest jemand die
        // Änderungen am Dienst und sucht sie vergeblich in der Oberfläche.
        if (TEIL_GATEWAY.test(text)) {
            return 'An der Erweiterung selbst hat sich nichts geändert – diese '
                + 'Fassung betrifft den Gateway-Dienst auf dem Rechner der Gemeinde.';
        }
        return text;                  // ältere Fassung ohne Teile
    }
    // Ab der ZEILE nach der Überschrift - sonst bliebe ihr Rest („(in
    // ChurchTools)") als eigene Zeile im Fenster stehen.
    const abTreffer = text.slice(treffer.index);
    const zeilenende = abTreffer.indexOf('\n');
    const ab = zeilenende >= 0 ? abTreffer.slice(zeilenende + 1) : '';
    const naechster = ab.search(/^##\s+/m);
    return naechster >= 0 ? ab.slice(0, naechster) : ab;
}

export function parseChangelog(md: string): ChangelogZeile[] {
    let text = String(md ?? '');
    // Neue Form: Der Changelog steht oben, die Endmarke schließt ihn ab.
    const e = text.indexOf(ENDE_MARKER);
    const i = text.indexOf(MARKER);
    if (e >= 0) {
        text = text.slice(0, e);
        // Steht die alte Startmarke ebenfalls davor, beginnt der Changelog dort.
        if (i >= 0 && i < e) text = text.slice(i + MARKER.length);
    } else if (i >= 0) {
        // Alte Form: alles hinter der Startmarke.
        text = text.slice(i + MARKER.length);
    } else {
        // Ältere Veröffentlichungen tragen die Marke noch nicht. Dann beginnt
        // der Changelog bei der ersten Überschrift; alles davor ist Einleitung.
        // Fehlt auch die, bleibt der Text vollständig – lieber zu viel zeigen
        // als versehentlich alles wegzuschneiden.
        const h = text.search(/^#{2,3}\s+/m);
        if (h > 0) text = text.slice(h);
    }

    text = nurErweiterung(text);
    const tiefeMitVersionen = /^####\s+/m.test(text);

    const raus: ChangelogZeile[] = [];
    for (const roh of text.split(/\r?\n/)) {
        const zeile = roh.trimEnd();
        if (!zeile.trim()) continue;
        // Sterne der Auszeichnung entfernen – sie werden nicht gerendert.
        // Auszeichnungen entfernen - sie werden nicht gerendert und stuenden
        // sonst als Sternchen und Unterstriche im Text.
        const ohneFett = (t: string) => t.replace(/\*\*/g, '').replace(/(^|\s)_|_(\s|$)/g, '$1$2').trim();

        // Reihenfolge: erst die tiefste Ebene prüfen, sonst schluckt `##`
        // jede Überschrift.
        if (/^####\s+/.test(zeile)) { raus.push({ art: 'gruppe', text: ohneFett(zeile.replace(/^#+\s+/, '')) }); continue; }
        if (/^###\s+/.test(zeile)) {
            // Seit 26.10 gliedert die Beschreibung nach Version (###) und
            // darunter nach Gruppe (####). Vorher war ### die Gruppe - daran
            // zu erkennen, dass es gar keine vierte Ebene gibt.
            raus.push({ art: tiefeMitVersionen ? 'version' : 'gruppe',
                        text: ohneFett(zeile.replace(/^#+\s+/, '')) });
            continue;
        }
        if (/^##\s+/.test(zeile)) { raus.push({ art: 'version', text: ohneFett(zeile.replace(/^#+\s+/, '')) }); continue; }
        // Eingerückter Punkt = Eintrag, Punkt am Zeilenanfang = Bereich.
        const punkt = /^(\s*)[*-]\s+(.*)$/.exec(zeile);
        if (punkt) {
            const eingerueckt = punkt[1].length > 0;
            raus.push({ art: eingerueckt ? 'eintrag' : 'bereich', text: ohneFett(punkt[2]) });
            continue;
        }
        raus.push({ art: 'text', text: ohneFett(zeile) });
    }
    return raus;
}
