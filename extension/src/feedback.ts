/**
 * Feedback & automatische Fehlermeldung.
 *
 * Da eine ChurchTools-Extension nur im Browser läuft, kann sie selbst keine
 * E-Mail senden. Deshalb:
 *  - Ist ein Endpunkt konfiguriert (VITE_FEEDBACK_URL, z. B. Formspree/Web3Forms
 *    oder ein eigener Webhook), werden Feedback UND Fehler dorthin per POST
 *    geschickt → landen zentral im Postfach des Betreibers. Für Tests mit
 *    mehreren Personen der empfohlene Weg.
 *  - Ohne Endpunkt öffnet das Feedback-Formular eine vorbefüllte E-Mail
 *    (mailto) an FEEDBACK_EMAIL. Automatische Fehlermeldungen sind ohne Endpunkt
 *    nur lokal (Badge am Feedback-Knopf), da ein Browser nicht ungefragt mailen
 *    kann.
 */
export const FEEDBACK_URL: string = (import.meta.env.VITE_FEEDBACK_URL || '').trim();
export const FEEDBACK_EMAIL = 'josua.hess@icloud.com';
// Wird beim Build aus git describe gesetzt (vite.config.ts define).
declare const __APP_VERSION__: string;
export const APP_VERSION: string = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev';

export interface ReportContext {
    version: string;
    instance: string;      // Host der ChurchTools-Instanz
    device: string;        // maskierte Seriennummer (kein Geheimnis)
    online: boolean | null;
    userAgent: string;
    logTail: string[];
}

export function maskSerial(serial?: string): string {
    if (!serial) return '(keins)';
    return serial.length <= 4 ? serial : serial.slice(0, 3) + '••••' + serial.slice(-2);
}

async function post(payload: unknown): Promise<boolean> {
    if (!FEEDBACK_URL) return false;
    try {
        const res = await fetch(FEEDBACK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(payload),
        });
        return res.ok;
    } catch {
        return false;
    }
}

// einfache Entprellung, damit derselbe Fehler nicht wiederholt gemeldet wird
const seen = new Map<string, number>();
function throttled(key: string, ms = 60000): boolean {
    const now = Date.now();
    const last = seen.get(key) ?? 0;
    if (now - last < ms) return true;
    seen.set(key, now);
    return false;
}

/** Automatische Fehlermeldung. Gibt zurück, ob sie versendet werden konnte. */
export async function reportError(where: string, error: unknown, ctx: ReportContext): Promise<boolean> {
    const message = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? error.stack : undefined;
    if (throttled(where + '|' + message)) return true; // schon kürzlich gemeldet
    return post({
        type: 'error',
        where,
        message,
        stack,
        at: new Date().toISOString(),
        ...ctx,
    });
}

export interface FeedbackFields {
    name: string;
    email: string;
    category: string;
    message: string;
}

/**
 * Feedback absenden. Ergebnis:
 *  - { sent: true } wenn per Endpunkt verschickt
 *  - { sent: false, mailto } wenn kein/gescheiterter Endpunkt → UI öffnet mailto
 */
export async function submitFeedback(
    f: FeedbackFields,
    ctx: ReportContext,
): Promise<{ sent: boolean; mailto?: string }> {
    const ok = await post({ type: 'feedback', ...f, at: new Date().toISOString(), ...ctx });
    if (ok) return { sent: true };

    const subject = `Glockensteuerung Feedback: ${f.category || 'Allgemein'}`;
    const body =
        `${f.message}\n\n` +
        `— — —\nVon: ${f.name || '(anonym)'} <${f.email || ''}>\n` +
        `Instanz: ${ctx.instance}\nGerät: ${ctx.device}\nVersion: ${ctx.version}\n` +
        `Online: ${ctx.online}\n\nLetzte Ereignisse:\n${ctx.logTail.join('\n')}`;
    const mailto = `mailto:${FEEDBACK_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    return { sent: false, mailto };
}
