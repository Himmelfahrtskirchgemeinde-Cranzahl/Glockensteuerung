/**
 * Hell oder dunkel - dem Thema von ChurchTools folgen.
 *
 * Bisher war die Erweiterung immer hell. Steht ChurchTools auf dunkel, faerbt
 * es Text weiss - und der stand dann auf unseren weissen Karten. Manche Zeilen
 * waren dadurch gar nicht mehr zu lesen.
 *
 * Woran erkennt man das Thema? ChurchTools sagt es nicht ueber seine
 * Schnittstelle, und wie es die Umschaltung im Aufbau der Seite vermerkt, kann
 * sich mit jeder Fassung aendern. Darum wird zuerst das genommen, was sich
 * nicht umbenennen laesst: die TATSAECHLICHE Farbe der Flaeche, auf der das
 * Modul liegt. Ist sie dunkel, ist das Thema dunkel - egal, wie die Klasse
 * gerade heisst.
 *
 * Reihenfolge:
 *   1. Gemessene Flaeche (im iframe: die Umgebung des Rahmens; sonst: der
 *      Elternknoten des Moduls)
 *   2. Uebliche Kennzeichen am Dokument (data-theme, Klasse "dark" ...)
 *   3. Einstellung des Betriebssystems
 *
 * Ergebnis landet als Attribut `data-thema` am <html> des Moduls; app.css
 * haengt die dunkle Farbpalette daran.
 *
 * WICHTIG fuer spaetere Aenderungen: Das Modul faerbt `html` und `body`
 * bewusst NICHT ein. Wuerde es das tun, maesse Schritt 1 die eigene Farbe und
 * bestaetigte sich selbst. Die Flaeche traegt `.gs`, nicht das Dokument.
 */
export type Thema = 'hell' | 'dunkel';

/** Ab welcher Helligkeit gilt eine Flaeche als dunkel (0 = schwarz, 1 = weiss). */
const DUNKEL_UNTER = 0.35;

/** Attribute, in denen Oberflaechen ueblicherweise ihr Thema vermerken. */
const KENNZEICHEN = ['data-theme', 'data-color-scheme', 'data-mode', 'data-bs-theme', 'color-scheme'];

/** Wie weit die Suche nach einer gefuellten Flaeche nach oben laeuft. */
const MAX_TIEFE = 30;

interface Befund {
    dunkel: boolean;
    quelle: string;
}

let aktuell: Thema | null = null;
let letzteQuelle = 'noch nicht bestimmt';

/** Was zuletzt erkannt wurde - wird beim Start ins Ereignis-Log geschrieben. */
export function themaInfo(): { thema: Thema; quelle: string } {
    return { thema: aktuell ?? 'hell', quelle: letzteQuelle };
}

/** 'rgb(r, g, b)' / 'rgba(r, g, b, a)' zerlegen. Alles andere: null. */
function zerlegen(wert: string): [number, number, number, number] | null {
    const m = wert.match(/^rgba?\(([^)]+)\)$/i);
    if (!m) return null;
    const t = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    if (t.length < 3 || t.slice(0, 3).some((n) => Number.isNaN(n))) return null;
    const a = t.length > 3 && !Number.isNaN(t[3]) ? t[3] : 1;
    return [t[0], t[1], t[2], a];
}

/** Wahrgenommene Helligkeit nach WCAG - nicht der Mittelwert der Kanaele. */
function helligkeit(r: number, g: number, b: number): number {
    const k = (c: number): number => {
        const s = c / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * k(r) + 0.7152 * k(g) + 0.0722 * k(b);
}

/**
 * Von `start` aus nach oben die erste Flaeche suchen, die wirklich gefuellt
 * ist. Durchsichtige Elemente sagen nichts ueber die Farbe aus, auf der man
 * am Ende steht.
 */
function gemesseneFlaeche(start: Element | null): Befund | null {
    const sicht = start?.ownerDocument?.defaultView;
    if (!sicht) return null;
    let el: Element | null = start;
    for (let i = 0; el && i < MAX_TIEFE; i++, el = el.parentElement) {
        let rgb: ReturnType<typeof zerlegen> = null;
        try {
            rgb = zerlegen(sicht.getComputedStyle(el).backgroundColor);
        } catch {
            return null; // Dokument zwischenzeitlich nicht mehr lesbar
        }
        if (!rgb || rgb[3] < 0.5) continue;
        const h = helligkeit(rgb[0], rgb[1], rgb[2]);
        return {
            dunkel: h < DUNKEL_UNTER,
            quelle: `Flaeche von <${el.tagName.toLowerCase()}> (Helligkeit ${h.toFixed(2)})`,
        };
    }
    return null;
}

/** Uebliche Kennzeichen am Dokument - falls keine Flaeche gefuellt war. */
function kennzeichen(doc: Document): Befund | null {
    for (const el of [doc.documentElement, doc.body]) {
        if (!el) continue;
        for (const name of KENNZEICHEN) {
            const v = el.getAttribute(name);
            if (!v) continue;
            if (/dark/i.test(v)) return { dunkel: true, quelle: `${name}="${v}"` };
            if (/light/i.test(v)) return { dunkel: false, quelle: `${name}="${v}"` };
        }
        for (const klasse of Array.from(el.classList)) {
            if (/(^|-)dark($|-)/i.test(klasse)) return { dunkel: true, quelle: `Klasse "${klasse}"` };
            if (/(^|-)light($|-)/i.test(klasse)) return { dunkel: false, quelle: `Klasse "${klasse}"` };
        }
    }
    return null;
}

/** Letzter Rueckfall: was der Rechner selbst eingestellt hat. */
function systemeinstellung(): Befund {
    let dunkel = false;
    try {
        dunkel = window.matchMedia?.('(prefers-color-scheme: dark)').matches === true;
    } catch {
        /* alte Browser ohne matchMedia - dann eben hell */
    }
    return { dunkel, quelle: 'Einstellung des Rechners' };
}

/**
 * Das Dokument, in dem ChurchTools liegt, und der Punkt, an dem die Suche nach
 * der Flaeche beginnt. Im iframe ist das der Rahmen selbst, sonst der
 * Elternknoten des Moduls.
 */
function umgebung(): { doc: Document; start: Element | null } {
    try {
        const rahmen = window.frameElement as Element | null;
        if (rahmen?.ownerDocument) return { doc: rahmen.ownerDocument, start: rahmen };
    } catch {
        /* fremde Herkunft: das Elternfenster ist nicht lesbar */
    }
    const app = document.getElementById('app');
    return { doc: document, start: app?.parentElement ?? document.body };
}

function anwenden(befund: Befund): void {
    const thema: Thema = befund.dunkel ? 'dunkel' : 'hell';
    letzteQuelle = befund.quelle;
    if (thema === aktuell) return;
    aktuell = thema;
    const wurzel = document.documentElement;
    wurzel.setAttribute('data-thema', thema);
    // Damit auch das, was der Browser selbst zeichnet - Rollbalken, Datums- und
    // Zeitfelder, die Flaeche hinter dem Inhalt - zum Thema passt.
    wurzel.style.colorScheme = thema === 'dunkel' ? 'dark' : 'light';
}

function pruefen(): void {
    const u = umgebung();
    anwenden(gemesseneFlaeche(u.start) ?? kennzeichen(u.doc) ?? systemeinstellung());
}

let gestartet = false;

/**
 * Thema einmal bestimmen und danach mitziehen, wenn ChurchTools umgeschaltet
 * wird - ohne dass die Seite neu geladen werden muss.
 */
export function themaFolgen(): void {
    pruefen();
    // ChurchTools baut seine Flaechen teils erst nach dem Laden auf - genau wie
    // bei der Hoehenmessung ein paar Mal nachfassen.
    [50, 150, 400, 1000, 2000].forEach((d) => setTimeout(pruefen, d));
    if (gestartet) return;
    gestartet = true;

    try {
        window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', pruefen);
    } catch {
        /* nicht schlimm - dann bleibt es beim Stand vom Laden */
    }

    if (typeof MutationObserver === 'undefined') return;
    const u = umgebung();
    const beobachter = new MutationObserver(() => pruefen());
    const was = { attributes: true, attributeFilter: ['class', 'style', ...KENNZEICHEN] };
    try {
        beobachter.observe(u.doc.documentElement, was);
        if (u.doc.body) beobachter.observe(u.doc.body, was);
        // Manche Oberflaechen tauschen zum Umschalten ein ganzes Stylesheet aus.
        if (u.doc.head) beobachter.observe(u.doc.head, { childList: true });
    } catch {
        /* nicht beobachtbar - dann bleibt es beim Stand vom Laden */
    }
}
