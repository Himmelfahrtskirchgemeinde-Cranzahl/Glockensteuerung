/**
 * Regeln des Ereignis-Logs – ohne Oberfläche, damit sie prüfbar sind.
 *
 * Zwei Dinge passieren hier, und beide gehen leicht schief:
 *
 * 1. **Zusammenführen vor dem Schreiben.** Das Log liegt als EIN Eintrag in
 *    ChurchTools. Wer ihn schreibt, überschreibt alles darin. Sind zwei Seiten
 *    offen, verlöre die zweite die Zeilen der ersten – deshalb wird vorher
 *    frisch gelesen und beides gemischt.
 * 2. **Doppelte erkennen.** Nach dem Wegschreiben steht dieselbe Zeile sowohl
 *    in dieser Sitzung als auch im geladenen Stand. Ohne Erkennung stünde jede
 *    Zeile zweimal da.
 *
 * Erkannt wird an Zeitstempel **und** Text. Nur die Zeit reicht nicht: Beim
 * Verbinden entstehen mehrere Zeilen in derselben Sekunde.
 */
import type { LogEntry } from './config';

/** Eine Zeile, wie sie angezeigt wird. */
export type LogDir = 'in' | 'out' | 'sim' | 'info' | 'gw';
export type Zeile = { ts: Date; dir: LogDir; line: string; wer?: string };

const ARTEN: LogDir[] = ['in', 'out', 'sim', 'info', 'gw'];

/** Zeichen je Ereignisart, die der Gateway-Dienst festhaelt. */
const GW_ART: Record<string, LogDir> = {
    laeuten: 'out',
    sim: 'sim',
    an: 'info',
    aus: 'gw',
    info: 'info',
};

/**
 * Aeltere Dienste (bis einschliesslich 26.10.1) kannten die Art „laeuten"
 * noch nicht und legten jedes Ausloesen als „info" ab. Solche Zeilen stehen
 * noch wochenlang im gespeicherten Log - und ein Dienst, der noch nicht
 * aktualisiert wurde, schreibt sie weiter. Am Satzanfang sind sie eindeutig,
 * deshalb werden sie daran erkannt statt als blasse Information stehen zu
 * bleiben.
 */
const ALT_LAEUTEN = /^Ausgel(ö|oe)st:/;
const ALT_SIM = /^Simulation:/;

/** Welches Zeichen ein Gateway-Ereignis bekommt. */
export function gatewayArt(art: string, text: string): LogDir {
    if (art === 'info') {
        if (ALT_LAEUTEN.test(text)) return 'out';
        if (ALT_SIM.test(text)) return 'sim';
    }
    return GW_ART[art] ?? 'info';
}

/** Neue Zeilen an den gespeicherten Stand anfügen, neueste zuerst. */
export function zusammenfuehren(vorhanden: LogEntry[], neue: LogEntry[], max: number): LogEntry[] {
    const schluessel = (e: LogEntry) => `${e.at}|${e.text}`;
    const bekannt = new Set(vorhanden.map(schluessel));
    const frisch = neue.filter((e) => {
        if (bekannt.has(schluessel(e))) return false;
        bekannt.add(schluessel(e));        // auch innerhalb der neuen Zeilen
        return true;
    });
    return [...frisch, ...vorhanden]
        .sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
        .slice(0, max);
}

/** Gespeicherte Einträge in Anzeigezeilen – unlesbare Zeitstempel fliegen raus. */
export function zuZeilen(eintraege: LogEntry[]): Zeile[] {
    return eintraege
        .map((e) => ({
            ts: new Date(e.at),
            dir: (ARTEN.includes(e.art as LogDir) ? e.art : 'info') as LogDir,
            line: e.text,
            wer: e.wer,
        }))
        .filter((e) => Number.isFinite(e.ts.getTime()));
}

/** Mehrere Quellen zu einer Liste – ohne Doppelte, neueste zuerst. */
export function ohneDoppelte(...quellen: Zeile[][]): Zeile[] {
    const gesehen = new Set<string>();
    const raus: Zeile[] = [];
    for (const zeile of quellen.flat()) {
        const schluessel = `${zeile.ts.getTime()}|${zeile.line}`;
        if (gesehen.has(schluessel)) continue;
        gesehen.add(schluessel);
        raus.push(zeile);
    }
    return raus.sort((a, b) => b.ts.getTime() - a.ts.getTime());
}

/* ---------------------------------------------------------------------------
 * Wochenblöcke
 *
 * ChurchTools begrenzt jeden Eintrag im Schlüssel-Wert-Speicher auf **10 000
 * Zeichen**. Das Log lag bisher als EIN Eintrag dort – bei 300 Zeilen sind das
 * rund 35 000. Die Folge war kein halb gespeichertes Log, sondern gar keines:
 * Jeder Schreibversuch endete mit „400 – Eingabe muss ein Text sein, der
 * zwischen 0 und 10000 Zeichen enthält", und das Log lebte wieder nur in der
 * geöffneten Seite.
 *
 * Deshalb liegt es jetzt in Blöcken – einer je Kalenderwoche (`log-2026-W38`).
 * Das löst zwei Dinge auf einmal: Jeder Block bleibt klein genug, und alte
 * Wochen lassen sich als Ganzes wegräumen, ohne im Bestand zu schneiden.
 *
 * Gelesen wird trotzdem in EINER Abfrage: Die API liefert alle Einträge einer
 * Kategorie zusammen.
 * ------------------------------------------------------------------------ */

/** Vorsilbe aller Wochenblöcke. Der alte Schlüssel hieß schlicht `log`. */
export const LOG_PRAEFIX = 'log-';
/** Der Schlüssel, unter dem das Log vor den Wochenblöcken lag. */
export const LOG_ALT = 'log';

/**
 * Kalenderwoche nach ISO 8601 – gerechnet in der Zeit des Betrachters.
 *
 * Bewusst lokal und nicht UTC: Wer sonntags um 23:30 Uhr läutet, erwartet das
 * in der Woche dieses Sonntags, nicht in der nächsten.
 */
function isoWoche(d: Date): { jahr: number; woche: number } {
    // Auf UTC-Mitternacht des lokalen Kalendertags normieren. Damit spielt die
    // Sommerzeit keine Rolle mehr - die Differenz zweier Tage ist dann immer
    // ein Vielfaches von 24 Stunden.
    const tag = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    const t = new Date(tag);
    const wochentag = t.getUTCDay() || 7;            // Mo = 1 … So = 7
    t.setUTCDate(t.getUTCDate() + 4 - wochentag);    // auf den Donnerstag
    const jahresanfang = Date.UTC(t.getUTCFullYear(), 0, 1);
    const woche = Math.ceil(((t.getTime() - jahresanfang) / 86400000 + 1) / 7);
    return { jahr: t.getUTCFullYear(), woche };
}

/** Schlüssel des Blocks, in den ein Zeitstempel gehört: `log-2026-W38`. */
export function wochenSchluessel(at: string): string {
    const d = new Date(at);
    if (!Number.isFinite(d.getTime())) return `${LOG_PRAEFIX}unbekannt`;
    const { jahr, woche } = isoWoche(d);
    return `${LOG_PRAEFIX}${jahr}-W${String(woche).padStart(2, '0')}`;
}

/** Ist das ein Eintrag des Logs? (Wochenblock oder der alte Sammel-Eintrag) */
export function istLogSchluessel(key: string): boolean {
    return key === LOG_ALT || key.startsWith(LOG_PRAEFIX);
}

/**
 * Die Woche zu einem Schlüssel: `log-2026-W38-2` -> `2026-W38`.
 *
 * Eine Woche kann auf mehrere Einträge verteilt sein (siehe `aufteilen`).
 * Aufbewahrt und weggeräumt wird trotzdem in Wochen, nicht in Einträgen.
 */
export function wocheVon(key: string): string {
    if (key === LOG_ALT) return '';
    const m = /^log-(\d{4}-W\d{2})(?:-\d+)?$/.exec(key);
    return m ? m[1] : 'unbekannt';
}

/** Schlüssel des n-ten Teils einer Woche – der erste heißt wie die Woche. */
export function teilSchluessel(woche: string, nr: number): string {
    return nr <= 1 ? `${LOG_PRAEFIX}${woche}` : `${LOG_PRAEFIX}${woche}-${nr}`;
}

/**
 * Wochen nach Alter – die neueste zuerst.
 *
 * Die Schlüssel sind so gebaut, dass alphabetisch = chronologisch gilt
 * (vierstelliges Jahr, zweistellige Woche). Der alte Sammel-Eintrag und alles
 * Unlesbare zählen als das Älteste: Was dort liegt, stammt aus der Zeit davor.
 */
export function wochenNachAlter(schluessel: string[]): string[] {
    const wochen = [...new Set(schluessel.map(wocheVon))];
    return wochen.sort((a, b) => {
        const rang = (w: string) => (/^\d{4}-W\d{2}$/.test(w) ? 1 : 0);
        if (rang(a) !== rang(b)) return rang(b) - rang(a);
        return a < b ? 1 : a > b ? -1 : 0;
    });
}

/** Einträge auf die Wochen verteilen, in die sie gehören. */
export function nachWochen(eintraege: LogEntry[]): Map<string, LogEntry[]> {
    const raus = new Map<string, LogEntry[]>();
    for (const e of eintraege) {
        const key = wochenSchluessel(e.at);
        const liste = raus.get(key);
        if (liste) liste.push(e);
        else raus.set(key, [e]);
    }
    return raus;
}

/**
 * Verteilt die Zeilen einer Woche auf so viele Einträge, wie sie braucht.
 *
 * Ein Eintrag fasst höchstens `maxZeichen`; ist die Woche voller, entsteht ein
 * zweiter (`log-2026-W38-2`). Das ist der Unterschied zwischen „das Log ist
 * voll" und „diese Woche war viel los": Eine Festwoche mit Christvesper,
 * Silvester und Neujahr passt sonst nicht in einen einzigen Eintrag, und die
 * ältesten Zeilen fielen ausgerechnet dann weg.
 *
 * Nach `maxTeile` ist Schluss – irgendwo muss die Grenze sein, sonst füllte
 * ein Fehler, der sich im Minutentakt wiederholt, den Speicher der Gemeinde.
 * Dann fallen die ältesten Zeilen dieser Woche weg.
 *
 * Gemessen wird an genau der Zeichenkette, die später geschrieben wird. Alles
 * andere wäre geraten: Ein Umlaut oder ein langer Termin-Titel verschiebt die
 * Rechnung sofort.
 */
export function aufteilen(
    woche: string, eintraege: LogEntry[], maxZeichen: number, maxTeile: number,
): Map<string, LogEntry[]> {
    const raus = new Map<string, LogEntry[]>();
    const laenge = (key: string, liste: LogEntry[]) => JSON.stringify({ key, data: liste }).length;
    let rest = eintraege;
    for (let nr = 1; nr <= maxTeile && rest.length; nr++) {
        const key = teilSchluessel(woche, nr);
        let passt: LogEntry[] = [];
        for (const e of rest) {
            const versuch = [...passt, e];
            if (laenge(key, versuch) > maxZeichen) break;
            passt = versuch;
        }
        // Eine einzelne Zeile, die für sich schon zu lang ist, würde die
        // Schleife ewig drehen lassen - sie wird gekürzt statt übersprungen,
        // damit nichts stumm verschwindet.
        if (!passt.length) {
            const zuLang = rest[0];
            const platz = Math.max(0, maxZeichen - laenge(key, [{ ...zuLang, text: '' }]) - 3);
            passt = [{ ...zuLang, text: zuLang.text.slice(0, platz) + '...' }];
        }
        raus.set(key, passt);
        rest = rest.slice(passt.length);
    }
    return raus;
}

/* ---------------------------------------------------------------------------
 * Suchen, filtern, einfärben
 *
 * Das Log hält inzwischen mehrere Wochen. Wer darin etwas sucht – „wann war
 * der Ausfall?", „hat jemand am Sonntag von Hand geläutet?" – scrollt sonst
 * durch hunderte Zeilen, von denen die meisten Betriebsmeldungen sind.
 * ------------------------------------------------------------------------ */

/** Wie ernst ist eine Zeile? Bestimmt ihre Farbe und den Schnellfilter. */
export type Schwere = 'fehler' | 'hinweis' | '';

/**
 * Was als Störung gilt – rot.
 *
 * Bewusst am Text und nicht an der Art: Ein Fehler kann in jeder Art stecken.
 * „Auslösen fehlgeschlagen" ist eine Antwort der Anlage, „Automatik antwortet
 * nicht mehr" eine Meldung über den Dienst – beides muss rot sein, sonst geht
 * es zwischen den Betriebszeilen unter.
 */
const FEHLER = /fehler|fehlgeschlagen|nicht erreichbar|antwortet nicht|meldet sich nicht|keine verbindung|verbindung verloren|abgebrochen|konnte nicht|kann nicht|abgelehnt|störung|verweigert|zeitüberschreitung/i;

/** Was Aufmerksamkeit verdient, aber keine Störung ist – gelb. */
const HINWEIS = /hinweis|achtung|ruhezeit|übersprungen|simulation|wäre jetzt|wird nicht|noch nie|startet gerade neu|aktualisiert sich|nur mitlesen/i;

export function schwere(zeile: Zeile): Schwere {
    if (FEHLER.test(zeile.line)) return 'fehler';
    if (HINWEIS.test(zeile.line)) return 'hinweis';
    return '';
}

/** Wonach im Ereignis-Log gesucht und gefiltert wird. */
export type LogFilter = {
    /** Freitext – gesucht wird im Ereignis UND im Namen der Person. */
    suche: string;
    /** Welche Arten gezeigt werden. Leer = alle. */
    arten: Set<LogDir>;
    /** Nur Fehler und Hinweise zeigen. */
    nurAuffaellig: boolean;
    /** Zeitraum in Millisekunden; `-Infinity`/`Infinity` = offen. */
    von: number;
    bis: number;
};

export function leererFilter(): LogFilter {
    return { suche: '', arten: new Set(), nurAuffaellig: false, von: -Infinity, bis: Infinity };
}

/** Ist gerade überhaupt etwas eingegrenzt? */
export function filterAktiv(f: LogFilter): boolean {
    return !!f.suche.trim() || f.arten.size > 0 || f.nurAuffaellig
        || Number.isFinite(f.von) || Number.isFinite(f.bis);
}

/**
 * Wendet den Filter an – Reihenfolge und Inhalt bleiben, es fällt nur weg.
 *
 * Die Suche zerlegt die Eingabe in Wörter, die ALLE vorkommen müssen (in
 * beliebiger Reihenfolge). „läuten josua" findet damit die Zeile, in der beides
 * steht, ohne dass jemand die genaue Formulierung kennen muss.
 */
export function filtern(zeilen: Zeile[], f: LogFilter): Zeile[] {
    const worte = f.suche.toLowerCase().split(/\s+/).filter(Boolean);
    return zeilen.filter((z) => {
        const t = z.ts.getTime();
        if (t < f.von || t > f.bis) return false;
        if (f.arten.size && !f.arten.has(z.dir)) return false;
        if (f.nurAuffaellig && !schwere(z)) return false;
        if (!worte.length) return true;
        const heuhaufen = `${z.line} ${z.wer ?? ''}`.toLowerCase();
        return worte.every((w) => heuhaufen.includes(w));
    });
}
