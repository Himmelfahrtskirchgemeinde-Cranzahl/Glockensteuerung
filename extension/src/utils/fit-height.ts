/**
 * Passt die Höhe des Extension-iframes an den Platz UNTER dem ChurchTools-
 * Header an. ChurchTools bettet Custom Modules same-origin in einem iframe ein,
 * gibt ihm aber keine feste Höhe – dadurch wächst das iframe mit dem Inhalt und
 * die GANZE Seite wird scrollbar (Kopfleiste + Seitenleiste scrollen mit).
 *
 * Da das iframe same-origin ist, dürfen wir von innen an `window.frameElement`
 * und `window.parent`. Wir setzen die iframe-Höhe auf
 *   Fensterhöhe − Abstand des iframes von oben (= ChurchTools-Header)
 * So bleibt die Shell exakt im sichtbaren Bereich; über `height:100%`
 * (html/body/#app/.gs) scrollt dann nur noch der Inhaltsbereich.
 *
 * Läuft das Modul nicht im iframe oder cross-origin, greift der CSS-Fallback
 * (height:100%).
 */
function apply(): void {
    try {
        const fe = window.frameElement as HTMLElement | null;
        if (!fe) return; // kein iframe → CSS-Fallback
        const parentWin = window.parent || window;
        const top = fe.getBoundingClientRect().top; // Abstand von oben = CT-Header
        const avail = parentWin.innerHeight - top;
        if (avail > 200) {
            const px = Math.round(avail) + 'px';
            fe.style.height = px;
            fe.style.maxHeight = px;
        }
    } catch {
        /* cross-origin o. Ä. – CSS-Fallback (height:100%) greift */
    }
}

let bound = false;
export function fitModuleHeight(): void {
    apply();
    // Nachziehen, falls ChurchTools die Höhe erst nach dem Laden setzt.
    [60, 200, 500, 1200].forEach((d) => setTimeout(apply, d));
    if (bound) return;
    bound = true;
    window.addEventListener('resize', apply, { passive: true });
    try {
        window.parent?.addEventListener('resize', apply, { passive: true });
    } catch {
        /* cross-origin – ignorieren */
    }
}
