/**
 * Begrenzt die Modul-Höhe auf den sichtbaren Bereich UNTER dem ChurchTools-
 * Header, damit Kopfleiste und Seitenleiste stehen bleiben und nur der
 * Inhaltsbereich scrollt.
 *
 * Warum überhaupt JavaScript? Reines CSS reicht nicht: ChurchTools gibt dem
 * Modul keine feste Höhe. `height:100%` löst sich dann auf die INHALTSHÖHE auf,
 * die Seite wird als Ganzes scrollbar – und `position:sticky` nützt nichts,
 * weil nicht der Inhalt, sondern das Modul selbst mitscrollt.
 *
 * Es werden zwei Einbettungsarten unterstützt:
 *  - iframe (same-origin): Höhe = Fensterhöhe des Elternfensters minus dem
 *    Abstand des iframes von oben (= genau der ChurchTools-Header). Die Höhe
 *    wird zusätzlich direkt am iframe gesetzt, sonst wächst es weiter mit.
 *  - eigenständig: Höhe = Fensterhöhe minus Abstand des Moduls von oben.
 *
 * Ergebnis landet als CSS-Variable `--gs-shell-h`, die `.gs` verwendet.
 * Kommt keine sinnvolle Messung zustande, greift der CSS-Fallback (100%).
 */
export interface FitInfo {
    mode: 'iframe' | 'eigenständig' | 'blockiert';
    height: number;
    detail: string;
}

let last: FitInfo = { mode: 'eigenständig', height: 0, detail: 'noch nicht gemessen' };

/** Letztes Messergebnis – wird beim Start ins Ereignis-Log geschrieben. */
export function fitInfo(): FitInfo {
    return last;
}

function frame(): HTMLElement | null {
    try {
        return (window.frameElement as HTMLElement | null) ?? null;
    } catch {
        return null; // cross-origin: Zugriff auf frameElement wirft
    }
}

function measure(): FitInfo {
    const fe = frame();
    if (fe) {
        try {
            const pw = window.parent;
            const top = fe.getBoundingClientRect().top;
            return {
                mode: 'iframe',
                height: Math.round(pw.innerHeight - top),
                detail: `Elternfenster ${pw.innerHeight}px, iframe ab ${Math.round(top)}px`,
            };
        } catch {
            return {
                mode: 'blockiert',
                height: Math.round(window.innerHeight),
                detail: 'Elternfenster nicht lesbar (cross-origin) – nutze eigene Fensterhöhe',
            };
        }
    }
    const root = document.getElementById('app') ?? document.body;
    const top = root.getBoundingClientRect().top + (window.scrollY || 0);
    return {
        mode: 'eigenständig',
        height: Math.round(window.innerHeight - top),
        detail: `Fenster ${window.innerHeight}px, Modul ab ${Math.round(top)}px`,
    };
}

function apply(): void {
    const info = measure();
    // Unsinnige Messungen (Modul noch nicht im Layout) nicht übernehmen –
    // sonst würde der Inhalt auf ein paar Pixel zusammengequetscht.
    if (info.height < 200) return;
    last = info;
    document.documentElement.style.setProperty('--gs-shell-h', `${info.height}px`);
    if (info.mode === 'iframe') {
        const fe = frame();
        if (fe) {
            fe.style.height = `${info.height}px`;
            fe.style.maxHeight = `${info.height}px`;
        }
    }
}

let started = false;
export function fitModuleHeight(): void {
    apply();
    // ChurchTools setzt die Höhe teils erst nach dem Laden – mehrfach nachziehen.
    [50, 150, 400, 1000, 2000].forEach((d) => setTimeout(apply, d));
    if (started) return;
    started = true;

    window.addEventListener('resize', apply, { passive: true });
    try {
        window.parent?.addEventListener('resize', apply, { passive: true });
    } catch {
        /* cross-origin – ignorieren */
    }

    // Falls ChurchTools die iframe-Höhe nachträglich überschreibt, erneut setzen.
    const fe = frame();
    if (fe && typeof MutationObserver !== 'undefined') {
        let busy = false;
        new MutationObserver(() => {
            if (busy) return; // eigene Änderung nicht erneut verarbeiten
            busy = true;
            requestAnimationFrame(() => { apply(); busy = false; });
        }).observe(fe, { attributes: true, attributeFilter: ['style', 'height'] });
    }
}
