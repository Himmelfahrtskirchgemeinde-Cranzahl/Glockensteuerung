/**
 * Marker im Kalendertitel: einzelne Laeutungen abschalten, ohne eine Regel
 * anzufassen.
 *
 * Im Titel eines Termins steht hinter einem Pluszeichen, was NICHT laeuten
 * soll:
 *
 *   Gottesdienst +AUSA      alles aus - fuer diesen Termin laeutet nichts
 *   Gottesdienst +AUSVL     nur die Regel mit dem Kuerzel "VL" faellt aus
 *   Gottesdienst +AUSVL +AUSNL   mehrere auf einmal
 *
 * Kurzform: statt "AUS" genuegt ein "A" - "+AVL" wirkt wie "+AUSVL", "+AA" wie
 * "+AUSA". Gross- und Kleinschreibung ist egal, und ein Doppelpunkt darf
 * dazwischen stehen (`+AUS:VL`).
 *
 * Ein Kuerzel gehoert IMMER dazu - entweder das einer Regel oder "A" fuer alle.
 * "+AUS" oder "+A" allein bewirkt nichts: Dort fehlt die Angabe, was
 * abgeschaltet werden soll, und ein halber Befehl soll nicht das ganze Gelaeut
 * abstellen.
 *
 * Die Kurzform greift NUR mit einem Kuerzel, das es wirklich gibt. Sonst risse
 * sie Loecher in gewoehnliche Titel: Aus "Konzert +Anmeldung erforderlich"
 * wuerde "Konzert erforderlich", und "nmeldung" galte als Kuerzel. "+AUS" ist
 * dagegen eindeutig genug, um immer zu wirken - auch mit einem Kuerzel, das es
 * nicht gibt (das ist ein Tippfehler, und der soll auffallen).
 *
 * WICHTIG: Der Marker wird aus dem Titel GESCHNITTEN, bevor er mit dem Titel
 * einer Regel verglichen wird. Sonst passte „Gottesdienst +AUSA" nicht mehr
 * auf die Regel „Gottesdienst" - der Marker haette dort zwar zufaellig die
 * richtige Wirkung, bei einer Regel ohne Titelfilter aber gar keine.
 *
 * Dieselbe Grammatik steht im Gateway in `gateway/marker.py`. Weichen die
 * beiden voneinander ab, zeigt die Vorschau etwas anderes an, als wirklich
 * laeutet - die Stellen gehoeren zusammen geaendert.
 */

/** Dieses Kuerzel steht fuer „alles" und darf keiner Regel gehoeren. */
export const ALLE = 'A';

/** Woraus ein Kuerzel bestehen darf. */
export const KUERZEL_ZEICHEN = /^[A-Za-z0-9ÄÖÜäöüß_-]+$/;

// Das Pluszeichen ist der Indikator, "AUS" (oder kurz "A") das Steuerwort.
// Beides zusammen kommt in einem Termin-Titel sonst nicht vor - anders als ein
// "+" allein. Die Reihenfolge in der Alternative ist wichtig: "AUS" wird zuerst
// versucht, sonst laese sich "+AUSVL" auch als "A" + Kuerzel "USVL".
const MUSTER = /\+(AUS|A)(?::?([A-Za-zÄÖÜäöüß0-9_-]+))?/gi;

export interface MarkerBefund {
    /** Titel ohne die Marker - damit wird gegen die Regel verglichen. */
    titel: string;
    /** Stand `+AUSA` (oder `+AUS`) darin? */
    allesAus: boolean;
    /** Genannte Kuerzel, in Grossbuchstaben, ohne das reservierte "A". */
    kuerzel: string[];
    /** Stand ueberhaupt ein Marker im Titel? */
    gefunden: boolean;
    /**
     * Stand `+AUS` ohne Kuerzel da? Das bewirkt nichts und ist fast immer ein
     * vergessenes „A".
     */
    ohneKuerzel: boolean;
}

/**
 * Titel zerlegen: was bleibt, und was soll ausfallen?
 *
 * `bekannte` sind die Kuerzel aller Regeln. Sie entscheiden allein ueber die
 * Kurzform `+A<Kuerzel>`; ohne sie wirkt nur das eindeutige `+AUS...`.
 */
export function markerLesen(roh: string | null | undefined,
                            bekannte: Array<string | null | undefined> = []): MarkerBefund {
    const text = (roh ?? '').toString();
    const befund: MarkerBefund = { titel: text.trim(), allesAus: false, kuerzel: [], gefunden: false, ohneKuerzel: false };
    if (!text.includes('+')) return befund;   // haeufigster Fall, ohne Regex

    const bekannt = new Set(bekannte.map((k) => (k ?? '').trim().toUpperCase()).filter(Boolean));
    const gesehen = new Set<string>();
    let rest = text.replace(MUSTER, (treffer, wortRoh?: string, gruppe?: string) => {
        const wort = (wortRoh ?? '').toUpperCase();
        const k = (gruppe ?? '').toUpperCase();
        if (!k) {
            // Ohne Kuerzel fehlt die Angabe, was abgeschaltet werden soll. Bei
            // der langen Form ist die Absicht aber erkennbar - das gehoert
            // gemeldet, sonst laeutet es und niemand weiss, warum.
            if (wort !== ALLE) befund.ohneKuerzel = true;
            return treffer;              // kein Marker: Text unangetastet
        }
        // Kurzform nur bei einem Kuerzel, das es gibt - sonst bliebe von
        // "+Anmeldung" ein Loch im Titel zurueck.
        if (wort === ALLE && k !== ALLE && !bekannt.has(k)) return treffer;
        befund.gefunden = true;
        if (k === ALLE) befund.allesAus = true;
        else if (!gesehen.has(k)) { gesehen.add(k); befund.kuerzel.push(k); }
        return ' ';
    });
    // Mehrfache Leerzeichen entstehen durch das Herausschneiden.
    rest = rest.replace(/\s{2,}/g, ' ').trim();
    befund.titel = rest;
    return befund;
}

/** Faellt die Regel mit diesem Kuerzel bei diesem Termin aus? */
export function regelAusgenommen(befund: MarkerBefund, kuerzel: string | null | undefined): boolean {
    if (befund.allesAus) return true;
    const k = (kuerzel ?? '').trim().toUpperCase();
    return k !== '' && befund.kuerzel.includes(k);
}

/**
 * Kuerzel, die im Titel stehen, aber zu keiner Regel gehoeren.
 *
 * Das ist der gefaehrliche Fall: Wer sich vertippt, glaubt, es laeute nicht -
 * und es laeutet doch. Deshalb muss er auffallen.
 */
export function unbekannteKuerzel(befund: MarkerBefund, bekannte: Array<string | null | undefined>): string[] {
    const liste = new Set(bekannte.map((k) => (k ?? '').trim().toUpperCase()).filter(Boolean));
    return befund.kuerzel.filter((k) => !liste.has(k));
}

/** Taugt der Text als Kuerzel einer Regel? Leer heisst „keines vergeben". */
export function kuerzelPruefen(roh: string, andere: Array<string | null | undefined>): string {
    const k = (roh ?? '').trim();
    if (!k) return '';
    if (!KUERZEL_ZEICHEN.test(k)) return 'Nur Buchstaben, Ziffern, - und _.';
    if (k.toUpperCase() === ALLE) return '„A" ist für +AUSA reserviert.';
    const belegt = andere.map((x) => (x ?? '').trim().toUpperCase()).filter(Boolean);
    if (belegt.includes(k.toUpperCase())) return 'Dieses Kürzel hat schon eine andere Regel.';
    return '';
}
