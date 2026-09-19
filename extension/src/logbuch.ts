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
