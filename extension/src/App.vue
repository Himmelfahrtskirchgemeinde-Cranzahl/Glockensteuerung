<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { churchtoolsClient } from '@churchtools/churchtools-client';
import { ConfigStore, newRule, newEmailConfig } from './config';
import type { CatKey, DeviceConfig, EmailConfig, GatewayStatus, MappingRule } from './config';
import { VocoMqtt, decodeName } from './voco/mqtt';
import { reportError, submitFeedback, maskSerial, APP_VERSION, FEEDBACK_URL } from './feedback';
import type { ReportContext, FeedbackFields } from './feedback';
import { loadRights } from './perms';
import { fetchLatest, isFresh, isNewer, parseChangelog, DOWNLOAD_URL, RELEASES_URL } from './update';
import type { UpdateCheck } from './update';
import type { Rights } from './perms';
import { fitInfo } from './utils/fit-height';

const isDev = import.meta.env.MODE === 'development';
declare const window: Window & typeof globalThis & { settings?: { base_url?: string } };
const baseUrl = window.settings?.base_url ?? import.meta.env.VITE_BASE_URL;

const store = new ConfigStore();
let voco: VocoMqtt | undefined;

type View = 'steuerung' | 'log' | 'regeln' | 'geraet' | 'email';
const view = ref<View>('steuerung');
/** Menü auf schmalen Schirmen ausgeklappt? Am Schreibtisch ohne Bedeutung. */
const navOffen = ref(false);

const rights = ref<Rights>({ isAdmin: false, manageExt: false, viewCats: [], editCats: [] });
const catIds = ref<Partial<Record<CatKey, number>>>({});
/** Sehen: Untermenü sichtbar / (bei Steuerung) läuten erlaubt. */
const canView = (cat: CatKey): boolean => {
    if (rights.value.isAdmin) return true;
    const id = catIds.value[cat];
    return id != null && rights.value.viewCats.includes(id);
};
/** Bearbeiten: Einstellungen ändern / scharfschalten. */
const canEdit = (cat: CatKey): boolean => {
    if (rights.value.isAdmin) return true;
    const id = catIds.value[cat];
    return id != null && rights.value.editCats.includes(id);
};
const showLaeuten = computed(() => canView('steuerung') || canView('log'));
const showEinstellungen = computed(() => canView('regeln') || rights.value.manageExt);
/** Sichtbarkeit einer Ansicht: „geraet" nur für „Erweiterung verwalten". */
const canSeeView = (v: View): boolean =>
    (v === 'geraet' || v === 'email' ? rights.value.manageExt : canView(v));
const allCatalogNames = computed(() => [...catalog.value.sPGS, ...catalog.value.melodies, ...catalog.value.programsteps]);
const simulate = ref(true);
const online = ref<boolean | null>(null);
const playable = ref<string[]>([]);
const stoppable = ref<string[]>([]);          // laufende (= stoppbare) Programme
const catalog = ref<{ sPGS: string[]; programsteps: string[]; melodies: string[] }>({ sPGS: [], programsteps: [], melodies: [] });
const runningSince = ref<Record<string, number>>({}); // roher Name -> Startzeit (ms)
const durations = ref<Record<string, number>>({});    // Anzeigename -> Minuten
const now = ref<number>(Date.now());
let clockTimer: number | undefined;
const device = ref<DeviceConfig>({ serial: '', devicePw: '', brokerUrl: 'wss://hew-voco.de:8084/mqtt' });
const rules = ref<MappingRule[]>([]);
const calendars = ref<{ id: number; name: string }[]>([]);
/** Zugang zum Postausgang. Nur für „Erweiterung verwalten" sichtbar. */
const email = ref<EmailConfig>(newEmailConfig());
const emailGeladen = ref(false);
const nextRingings = ref<Array<{ when: Date; program: string; source: string }>>([]);
/** Letztes Lebenszeichen des Gateway-Dienstes (schreibt er alle 2 Minuten). */
const gatewayStatus = ref<GatewayStatus | null>(null);
/** Ab wann gilt der Dienst als weg? Er meldet sich alle 2 min – 10 min sind großzügig. */
const GATEWAY_STALE_MIN = 10;
/** So oft das Lebenszeichen nachgeladen wird (der Dienst schreibt alle 2 min). */
const GATEWAY_POLL_MS = 120000;
let gatewayTimer: number | undefined;
/** Minuten seit dem letzten Lebenszeichen; null = noch nie eines gesehen. */
const gatewayAgeMin = computed<number | null>(() => {
    const at = gatewayStatus.value?.at;
    if (!at) return null;
    const t = new Date(at).getTime();
    if (!Number.isFinite(t)) return null;
    return Math.max(0, (now.value - t) / 60000);
});
/** Neueste veröffentlichte Version samt Changelog. */
const updateCheck = ref<UpdateCheck | null>(null);
/** Changelog-Fenster offen? */
const showChangelog = ref(false);
/** Wird der Changelog gerade nachgeladen? */
const changelogLaedt = ref(false);
/** Aufbereiteter Changelog für die Anzeige – ohne v-html, siehe update.ts. */
const changelog = computed(() => parseChangelog(updateCheck.value?.notes ?? ''));
/** Liegt eine neuere Fassung vor als die installierte? */
const updateAvailable = computed(() =>
    !!updateCheck.value && isNewer(updateCheck.value.latest, APP_VERSION),
);

/** Gibt es überhaupt Automatik, die ausfallen könnte? Ohne aktive Regel läutet
 *  nichts von allein – das ist dann so gewollt und keine Störung. */
const hasAutomation = computed(() => rules.value.some((r) => r.active && r.pgsName));
/** Kein Lebenszeichen oder zu altes -> Automatik läuft nicht. */
const gatewayDown = computed(() =>
    hasAutomation.value && (gatewayAgeMin.value === null || gatewayAgeMin.value > GATEWAY_STALE_MIN),
);
/** Erklärt, seit wann der Dienst fehlt. */
const gatewayDownText = computed(() => {
    const age = gatewayAgeMin.value;
    if (age === null) return 'Es ist noch nie ein Lebenszeichen eingegangen.';
    if (age < 90) return `Letztes Lebenszeichen vor ${Math.round(age)} Minuten.`;
    const h = Math.round(age / 60);
    return h < 48 ? `Letztes Lebenszeichen vor ${h} Stunden.` : `Letztes Lebenszeichen vor ${Math.round(h / 24)} Tagen.`;
});
/** Erklärt, WARUM die Vorschau leer ist (Ladefehler, keine Treffer, Schreibweise). */
const ringingHint = ref('');
type LogDir = 'in' | 'out' | 'sim' | 'info';
type LogEntry = { ts: Date; dir: LogDir; line: string };
const logLines = ref<LogEntry[]>([]);
const dlFrom = ref('');   // Log-Download: Von (datetime-local), leer = alles
const dlTo = ref('');     // Log-Download: Bis
const errorCount = ref(0);
const loading = ref(true);
const bootError = ref('');
const saveMsg = ref('');
const toastMsg = ref('');
let toastTimer: number | undefined;

const showFeedback = ref(false);
const fb = ref<FeedbackFields>({ name: '', email: '', category: 'Fehler / etwas funktioniert nicht', message: '' });

function ctx(): ReportContext {
    let instance = '';
    try { instance = new URL(baseUrl).host; } catch { instance = String(baseUrl); }
    return {
        version: APP_VERSION,
        instance,
        device: maskSerial(device.value.serial),
        online: online.value,
        userAgent: navigator.userAgent,
        logTail: logLines.value.slice(0, 15).map((e) => `${e.ts.toLocaleTimeString('de-DE')} ${e.dir} ${e.line}`),
    };
}

function pushLog(line: string, dir: LogDir) {
    logLines.value.unshift({ ts: new Date(), dir, line });
    if (logLines.value.length > 500) logLines.value.pop();
}

async function handleError(where: string, err: unknown) {
    pushLog('Fehler: ' + (err instanceof Error ? err.message : String(err)), 'info');
    const sent = await reportError(where, err, ctx());
    if (!sent && !FEEDBACK_URL) errorCount.value++;
}

function toast(msg: string) {
    toastMsg.value = msg;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => (toastMsg.value = ''), 2600);
}

/** Fehler lesbar machen – bei API-Fehlern inkl. Methode, URL, Status, Meldung. */
function describeError(e: unknown): string {
    const ax = e as { isAxiosError?: boolean; config?: { method?: string; url?: string }; response?: { status?: number; config?: { url?: string }; data?: { translatedMessage?: string; message?: string; errors?: { message?: string }[] } } };
    if (ax && (ax.isAxiosError || ax.response)) {
        const method = (ax.config?.method ?? '').toUpperCase();
        const url = ax.response?.config?.url ?? ax.config?.url ?? '';
        const status = ax.response?.status ?? '';
        const d = ax.response?.data;
        const detail = d?.errors?.[0]?.message ?? d?.translatedMessage ?? d?.message ?? '';
        return `${status} ${method} ${url}${detail ? ' – ' + detail : ''}`.trim();
    }
    return e instanceof Error ? e.message : String(e);
}

onMounted(() => {
    document.title = 'Glockensteuerung';
    window.addEventListener('error', (e) => handleError('window.onerror', e.error ?? e.message));
    window.addEventListener('unhandledrejection', (e) => handleError('promise', (e as PromiseRejectionEvent).reason));
    clockTimer = window.setInterval(() => (now.value = Date.now()), 10000);
    boot();
});

onUnmounted(() => {
    clearInterval(clockTimer);
    clearInterval(gatewayTimer);
    voco?.disconnect();
});

/**
 * Sucht nach einer neueren Fassung der Extension.
 *
 * Nur für „Erweiterung verwalten": Wer nicht aktualisieren darf, kann mit dem
 * Hinweis nichts anfangen – und jede ersparte Abfrage schont das GitHub-Limit
 * von 60 Abfragen je Stunde und IP. Ein einmal geholtes Ergebnis liegt einen
 * Tag im KV-Store, sodass EINE Abfrage für die ganze Gemeinde reicht.
 *
 * Schlägt etwas fehl, passiert schlicht nichts: Die Prüfung ist Beiwerk und
 * darf das Läuten nie stören.
 */
async function checkForUpdate() {
    try {
        // Den gespeicherten Stand liest JEDER: Er liegt in „steuerung", und der
        // Changelog soll allen offenstehen, die das Modul bedienen.
        const gespeichert = await store.loadUpdateCheck();
        if (gespeichert) updateCheck.value = gespeichert;

        // Bei GitHub nachfragen darf nur, wer die Erweiterung auch aktualisieren
        // kann – das hält die 60 Abfragen je Stunde und IP frei.
        if (!rights.value.manageExt) return;
        if (isFresh(gespeichert) && gespeichert?.notes) return;

        const frisch = await fetchLatest();
        if (!frisch) return;
        updateCheck.value = frisch;
        // Ohne Schreibrecht auf „steuerung" schlägt das fehl – dann fragt eben
        // jeder Aufruf selbst. Kein Grund, den Hinweis zu unterschlagen.
        store.saveUpdateCheck(frisch).catch(() => { /* Cache ist Beiwerk */ });
    } catch {
        /* Update-Prüfung darf nie stören */
    }
}

/**
 * Changelog-Fenster öffnen.
 *
 * Liegt noch kein Changelog vor – etwa weil noch nie ein Berechtigter das Modul
 * geöffnet hat –, wird er hier einmalig geholt. Das ist ein Klick, kein
 * Seitenaufruf, fällt beim Rate-Limit also kaum ins Gewicht.
 */
async function openChangelog() {
    showChangelog.value = true;
    if (updateCheck.value?.notes || changelogLaedt.value) return;
    changelogLaedt.value = true;
    try {
        const frisch = await fetchLatest();
        if (frisch) {
            updateCheck.value = frisch;
            if (rights.value.manageExt) {
                store.saveUpdateCheck(frisch).catch(() => { /* Cache ist Beiwerk */ });
            }
        }
    } catch {
        /* bleibt beim Hinweis „nicht abrufbar" im Fenster */
    } finally {
        changelogLaedt.value = false;
    }
}

/** Holt das Lebenszeichen erneut. Fehler bleiben still: Der alte Wert altert
 *  dann weiter, und genau das soll das Banner ja anzeigen. */
async function refreshGatewayStatus() {
    try {
        gatewayStatus.value = await store.loadGatewayStatus();
    } catch {
        /* kein Leserecht oder Netz weg – alter Stand bleibt stehen */
    }
}

async function boot() {
    try {
        if (isDev && import.meta.env.VITE_USERNAME) {
            await churchtoolsClient.post('/login', {
                username: import.meta.env.VITE_USERNAME,
                password: import.meta.env.VITE_PASSWORD,
            });
        }
        // Tab-Titel im ChurchTools-Stil: „‹Instanz› - Glockensteuerung".
        try {
            const info = await churchtoolsClient.get<{ siteName?: string }>('/info');
            if (info?.siteName) document.title = `${info.siteName} - Glockensteuerung`;
        } catch { /* Titel bleibt beim Fallback „Glockensteuerung" */ }
        await store.init();
        catIds.value = { ...store.catIds };
        rights.value = await loadRights();
        pickDefaultView();
        const cfg = await store.load();
        if (cfg.device) device.value = { brokerUrl: 'wss://hew-voco.de:8084/mqtt', ...cfg.device };
        rules.value = cfg.rules;
        durations.value = cfg.durations ?? {};
        gatewayStatus.value = cfg.gateway ?? null;
        // Regelmaessig nachladen – sonst altert der einmal geladene Wert vor sich
        // hin und das Warnbanner erschiene allein deshalb, weil die Seite offen ist.
        gatewayTimer = window.setInterval(refreshGatewayStatus, GATEWAY_POLL_MS);
        checkForUpdate();
        // Gemerkter Status gilt nur für Berechtigte; alle anderen bleiben in Simulation.
        simulate.value = rights.value.manageExt ? (cfg.simulate ?? true) : true;
        try { calendars.value = await churchtoolsClient.get<{ id: number; name: string }[]>('/calendars'); } catch { calendars.value = []; }
        loadNextRingings();
        if (device.value.serial && device.value.devicePw) connectVoco();
        // Wie wurde die Modulhöhe ermittelt? Steht im Log, falls Kopfleiste/
        // Seitenleiste doch mitscrollen – dann sieht man sofort, woran es liegt.
        const fit = fitInfo();
        pushLog(`Layout: ${fit.mode} – ${fit.detail} → Höhe ${fit.height}px`, 'info');
        loading.value = false;
    } catch (e) {
        loading.value = false;
        bootError.value = describeError(e);
        handleError('boot', e);
    }
}

function pickDefaultView() {
    const order: View[] = ['steuerung', 'log', 'regeln', 'geraet', 'email'];
    if (!canSeeView(view.value)) {
        const first = order.find((v) => canSeeView(v));
        if (first) view.value = first;
    }
}

function connectVoco() {
    voco?.disconnect();
    voco = new VocoMqtt(device.value);
    voco.simulate = simulate.value;
    voco.onLog = pushLog;
    voco.onUpdate = () => {
        online.value = voco!.status.online;
        playable.value = [...voco!.status.playable];
        updateRunning([...voco!.status.stoppable]);
        catalog.value = {
            sPGS: [...voco!.catalog.sPGS],
            programsteps: [...voco!.catalog.programsteps],
            melodies: [...voco!.catalog.melodies],
        };
    };
    pushLog('Verbinde mit Broker …', 'info');
    voco.connect().catch((e) => handleError('mqtt.connect', e));
}

function fire(raw: string) {
    if (!voco) return;
    if (simulate.value) { voco.start(raw); toast('Simulation: nichts gesendet – nur protokolliert.'); return; }
    if (confirm(`SCHARF: Programm wirklich AUSLÖSEN?\n\n${decodeName(raw)}\n\nDas löst echtes Läuten aus.`)) {
        voco.start(raw); toast('Befehl gesendet.');
    }
}

function setSimulate(on: boolean) {
    if (!on && !rights.value.manageExt) { toast('Nur mit der Berechtigung „Erweiterung verwalten" kann der Sicherheitsmodus deaktiviert werden.'); return; }
    if (!on && !confirm('Simulation ausschalten?\n\nDanach lösen Knöpfe und Automatik ECHTES Läuten aus.')) return;
    simulate.value = on;
    if (voco) voco.simulate = on;
    pushLog(on ? 'Simulation EIN – es wird nichts gesendet.' : 'Simulation AUS – Befehle werden real gesendet!', 'sim');
    store.saveSimulate(on).catch((e) => handleError('saveSimulate', e));
}

/** Verfolgt laufende (stoppbare) Programme: merkt Startzeit, loggt Start/Ende. */
function updateRunning(list: string[]) {
    const since = { ...runningSince.value };
    for (const raw of list) {
        if (since[raw] == null) { since[raw] = Date.now(); pushLog(`läuft: ${decodeName(raw)}`, 'in'); }
    }
    for (const raw of Object.keys(since)) {
        if (!list.includes(raw)) { pushLog(`beendet: ${decodeName(raw)}`, 'in'); delete since[raw]; }
    }
    runningSince.value = since;
    stoppable.value = list;
}

/** Anzeigetext „läuft" je Programm: Countdown wenn Dauer bekannt, sonst Laufzeit. */
function runningText(raw: string): string {
    const startedMs = runningSince.value[raw];
    const elapsedMin = startedMs ? (now.value - startedMs) / 60000 : 0;
    const dur = durations.value[decodeName(raw)] ?? durations.value[raw];
    if (dur && dur > 0) {
        const rem = Math.max(0, Math.ceil(dur - elapsedMin));
        return rem > 0 ? `noch ~${rem} min` : 'endet gleich';
    }
    return `läuft seit ${Math.max(0, Math.floor(elapsedMin))} min`;
}

function setDuration(displayName: string, minutes: number) {
    const map = { ...durations.value };
    if (minutes > 0) map[displayName] = minutes; else delete map[displayName];
    durations.value = map;
    store.saveDurations(map).catch((e) => handleError('saveDurations', e));
}

/** Log als Textdatei herunterladen; optional auf Zeitraum [von,bis] eingegrenzt. */
function downloadLog() {
    const from = dlFrom.value ? new Date(dlFrom.value).getTime() : -Infinity;
    const to = dlTo.value ? new Date(dlTo.value).getTime() : Infinity;
    const rows = logLines.value
        .filter((e) => e.ts.getTime() >= from && e.ts.getTime() <= to)
        .slice()
        .reverse()
        .map((e) => `${e.ts.toLocaleString('de-DE')}\t${e.dir}\t${e.line}`);
    if (rows.length === 0) { toast('Keine Log-Einträge im gewählten Zeitraum.'); return; }
    const header = `Glockensteuerung – Ereignis-Log (${rows.length} Einträge)\n`;
    const blob = new Blob([header + rows.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `glockensteuerung-log-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function requestSync() { voco?.requestSync(); }
function stopProgram(raw: string) {
    if (simulate.value) { voco?.stop(raw); toast('Simulation: nichts gesendet.'); }
    else if (confirm(`„${decodeName(raw)}“ wirklich stoppen?`)) voco?.stop(raw);
}
function stopAll() {
    if (simulate.value) { voco?.stopAll(); toast('Simulation: nichts gesendet.'); }
    else if (confirm('Wirklich ALLES stoppen?')) voco?.stopAll();
}

/**
 * Zugang zum Postausgang laden. Erst beim Öffnen der Seite, nicht beim Start:
 * Die Kategorie „email" ist für die meisten nicht lesbar, und ein unnötiger
 * Fehlversuch bei jedem Seitenaufruf hilft niemandem.
 */
async function loadEmail() {
    if (emailGeladen.value) return;
    emailGeladen.value = true;
    try {
        const cfg = await store.loadEmail();
        if (cfg) email.value = { ...newEmailConfig(), ...cfg };
    } catch (e) {
        handleError('loadEmail', e);
    }
}

async function saveEmail() {
    try {
        await store.saveEmail(email.value);
        toast('Postausgang gespeichert. Der Gateway übernimmt ihn beim nächsten Durchlauf.');
    } catch (e) { handleError('saveEmail', e); }
}

/**
 * Testnachricht in den Postausgang stellen.
 *
 * Verschickt wird sie vom Gateway – die Extension kann das nicht. Deshalb
 * bestätigt der Knopf auch nur das Einstellen, nicht den Versand; ob die Mail
 * ankam, zeigt das Postfach.
 */
async function testMail() {
    try {
        await store.queueMail({
            id: Math.random().toString(36).slice(2),
            subject: 'Testnachricht der Glockensteuerung',
            body: 'Wenn diese Nachricht ankommt, ist der Postausgang richtig eingerichtet.\n\n'
                + `Gesendet aus Version ${APP_VERSION}.`,
            at: new Date().toISOString(),
        });
        toast('Testnachricht eingestellt – der Gateway verschickt sie binnen einer Minute.');
    } catch (e) { handleError('testMail', e); }
}

async function saveDevice() {
    try {
        await store.saveDevice(device.value);
        connectVoco();
        toast('Gerät gespeichert – verbinde …');
    } catch (e) { handleError('saveDevice', e); }
}

function addRule() { rules.value.push(newRule()); }
function delRule(i: number) { rules.value.splice(i, 1); }
async function saveRules() {
    try {
        await store.saveRules(rules.value);
        saveMsg.value = '✓ gespeichert';
        loadNextRingings();
        setTimeout(() => (saveMsg.value = ''), 2500);
    } catch (e) { handleError('saveRules', e); }
}

function calId(rule: MappingRule, ev: Event) {
    const v = (ev.target as HTMLSelectElement).value;
    rule.calendarId = v ? Number(v) : null;
}

/**
 * Feedback abschicken.
 *
 * Erster Weg ist der Postausgang: Die Nachricht wird eingestellt, der Gateway
 * verschickt sie. Ob das überhaupt geht, sagt sein Lebenszeichen (`mail`) –
 * die Extension kann es nicht selbst beantworten, weil die Zugangsdaten in
 * einer Kategorie liegen, die normale Benutzer nicht lesen dürfen.
 *
 * Ist kein Postausgang eingerichtet oder klemmt das Einstellen, bleibt es beim
 * bisherigen Weg: zentraler Endpunkt, sonst das E-Mail-Programm.
 */
async function sendFeedback() {
    if (!fb.value.message.trim()) { toast('Bitte eine Nachricht eingeben.'); return; }
    const felder = fb.value;
    showFeedback.value = false;
    fb.value = { name: '', email: '', category: 'Fehler / etwas funktioniert nicht', message: '' };

    if (gatewayStatus.value?.mail) {
        try {
            const c = ctx();
            await store.queueMail({
                id: Math.random().toString(36).slice(2),
                subject: `Glockensteuerung – ${felder.category || 'Feedback'}`,
                body: `${felder.message}\n\n— — —\n`
                    + `Von: ${felder.name || '(ohne Namen)'} <${felder.email || 'keine Adresse'}>\n`
                    + `Instanz: ${c.instance}\nGerät: ${c.device}\nVersion: ${c.version}\n`
                    + `Gerät online: ${c.online}\n\nLetzte Ereignisse:\n${c.logTail.join('\n')}`,
                at: new Date().toISOString(),
            });
            toast('Danke! Die Nachricht wird gleich verschickt.');
            return;
        } catch {
            // Kein Schreibrecht o. Ä. – unten geht es auf dem alten Weg weiter.
        }
    }

    const res = await submitFeedback(felder, ctx());
    if (res.sent) toast('Danke! Feedback wurde gesendet.');
    else if (res.mailto) { toast('E-Mail-Programm wird geöffnet …'); window.location.href = res.mailto; }
    else toast('Konnte nicht senden.');
}

const logIcon = (d: string) => (d === 'in' ? '◀' : d === 'sim' ? '⚙' : d === 'info' ? 'ℹ' : '▶');

/** Steuerung zeigt nur ausgedünnte, wichtige Ereignisse: die eigenen Befehle
 *  (Läuten, Stoppen), echtes Läuten (Start/Ende), Simulationswechsel und
 *  Verbindungs-Infos (z. B. neu verbunden). Der ausführliche Verlauf (inkl.
 *  Status- und Katalog-Meldungen) steht im Ereignis-Log.
 *
 *  „out" MUSS dabei sein: Das sind die gesendeten Befehle – also genau das, was
 *  der Bedienende gerade getan hat. Ohne sie blieb das Läuten und Stoppen hier
 *  unsichtbar, und zwar ausgerechnet im scharfen Betrieb: In der Simulation
 *  wird stattdessen „sim" geloggt, das war zu sehen. */
const steuerungLog = computed(() =>
    logLines.value.filter(
        (e) =>
            e.dir === 'in' ||
            e.dir === 'out' ||
            e.dir === 'sim' ||
            (e.dir === 'info' && /verbind|verbunden|unterbroch|broker|fehler/i.test(e.line)),
    ),
);

const fmtDay = (d: Date) => d.toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' });
const fmtTime = (d: Date) => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });

/**
 * „Nächste automatische Läutungen" (Zeit = Beginn − Vorlauf).
 *
 * Nutzt bewusst DIESELBE Zuordnung wie der Gateway (gateway/scheduler.py,
 * `rule_matches`), damit die Vorschau nicht etwas anderes zeigt als real läutet:
 *  - Regel OHNE Titel → alle Termine der gewählten Kalender.
 *  - Regel MIT Titel  → nur Termine, deren Titel EXAKT übereinstimmt.
 *
 * Verglichen wird der TERMIN-TITEL, nicht die Veranstaltungsart: Eine Art lässt
 * sich einem Termin gar nicht zuweisen – sie hängt an einer verknüpften
 * Veranstaltung, die es in der Praxis meist nicht gibt. Dann fand die Vorschau
 * nie etwas. Der Titel steht dagegen immer am Termin.
 *
 * „Exakt" heißt: „Gottesdienst" trifft NUR „Gottesdienst" – nicht zusätzlich
 * „Festgottesdienst", nur weil das Wort darin vorkommt. Groß-/Kleinschreibung
 * und Leerzeichen am Rand werden ignoriert.
 *
 * Rein anzeigend – das echte Auslösen macht der Gateway.
 */
async function loadNextRingings() {
    nextRingings.value = [];
    ringingHint.value = '';
    const active = rules.value.filter((r) => r.active && r.pgsName);
    if (!active.length) return;

    const iso = (d: Date) => d.toISOString().slice(0, 10);
    const from = iso(new Date());
    const to = iso(new Date(Date.now() + 30 * 864e5));

    // Kalender der Regeln (ohne Kalenderangabe: alle sichtbaren).
    const calIds = new Set<number>();
    let needAll = false;
    for (const r of active) { if (r.calendarId) calIds.add(r.calendarId); else needAll = true; }
    if (needAll) for (const c of calendars.value) calIds.add(c.id);
    if (!calIds.size) { ringingHint.value = 'Keine Kalender verfügbar.'; return; }

    const p = new URLSearchParams();
    for (const id of calIds) p.append('calendar_ids[]', String(id));
    p.set('from', from);
    p.set('to', to);

    let items: any[] = [];
    try {
        const res = await churchtoolsClient.get<any>(`/calendars/appointments?${p.toString()}`);
        items = Array.isArray(res) ? res : (res?.data ?? []);
    } catch (e) {
        ringingHint.value = 'Termine konnten nicht geladen werden: ' + describeError(e);
        pushLog('Nächste Läutungen – ' + ringingHint.value, 'info');
        return;
    }

    const out: Array<{ when: Date; program: string; source: string }> = [];
    const seenTitles = new Set<string>();
    let appointments = 0;

    const add = (r: MappingRule, start: Date, source: string) => {
        const when = new Date(start.getTime() - (r.leadMinutes || 0) * 60000);
        if (when.getTime() < Date.now()) return;
        out.push({ when, program: r.pgsName, source });
    };

    for (const it of items) {
        const base = it?.appointment?.base ?? it?.base ?? it;
        // Bei Serienterminen trägt `base` das Datum des SERIENBEGINNS – das
        // Datum dieses Vorkommens steht in `calculated`. Immer erst dort schauen.
        const calc = it?.appointment?.calculated ?? it?.calculated;
        const startStr = calc?.startDate ?? base?.startDate;
        if (!startStr) continue;
        appointments++;
        const start = new Date(startStr);
        const calendarId: number | undefined = base?.calendar?.id;
        const calName: string = base?.calendar?.name ?? '';
        const title: string = String(base?.title ?? base?.caption ?? '').trim();
        if (title) seenTitles.add(title);

        for (const r of active) {
            if (r.calendarId && r.calendarId !== calendarId) continue;
            // Exakt vergleichen: „Festgottesdienst" ist NICHT „Gottesdienst".
            if (r.title && title.toLowerCase() !== r.title.trim().toLowerCase()) continue;
            add(r, start, `${title || '(ohne Titel)'} · Beginn ${fmtTime(start)} · Kalender „${calName}"`);
        }
    }

    out.sort((a, b) => a.when.getTime() - b.when.getTime());
    nextRingings.value = out.slice(0, 12);

    // Leere Liste nie unerklärt lassen – sonst sucht man den Fehler im Nichts.
    if (!out.length) {
        const wanted = [...new Set(active.filter((r) => r.title).map((r) => r.title!.trim()))];
        const vorhanden = [...seenTitles].slice(0, 12).join(', ')
            + (seenTitles.size > 12 ? ` … (+${seenTitles.size - 12})` : '');
        if (!appointments) {
            ringingHint.value = 'Im Zeitraum (30 Tage) liegen keine Termine in den gewählten Kalendern.';
        } else if (!wanted.length) {
            ringingHint.value = `${appointments} Termin(e) gefunden, aber alle liegen in der Vergangenheit oder in anderen Kalendern.`;
        } else {
            ringingHint.value = `Keine Übereinstimmung. Gesucht (exakt): ${wanted.join(', ')} – im Zeitraum vorhanden: ${vorhanden}. Die Schreibweise muss genau passen.`;
        }
        pushLog('Nächste Läutungen – ' + ringingHint.value, 'info');
    }
}
</script>

<template>
  <div class="gs">
    <!-- Ladezustand – 1:1 wie die ChurchTools-Modulanzeige -->
    <div v-if="loading" class="gs-loading">
      <div class="gs-loading-box">
        <svg class="gs-loading-mi" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/></svg>
        <div class="gs-loading-txt">Wird geladen …</div>
        <div class="gs-loading-dots"><span></span><span></span><span></span></div>
      </div>
    </div>

    <template v-else>
    <!-- Kopfleiste (voll breit, fix) -->
    <header class="gs-mhead">
        <!-- Nur auf schmalen Schirmen sichtbar (siehe app.css): klappt die
             Modul-Navigation als Menü aus, wie ChurchTools es selbst tut. -->
        <button class="gs-burger" type="button" :class="{ offen: navOffen }"
                :aria-expanded="navOffen" aria-controls="gs-nav"
                :title="navOffen ? 'Menü schließen' : 'Menü öffnen'"
                @click="navOffen = !navOffen">
          <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
        </button>
        <span class="mi">
          <svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>
        </span>
        <h1>Glockensteuerung</h1>
        <span class="sp"></span>
        <span v-if="!loading && !bootError" class="gs-pill" :class="simulate ? 'blue' : 'warn'">
          {{ simulate ? 'Simulation' : 'SCHARF' }}
        </span>
        <span v-if="online === true" class="gs-pill ok"><span class="dot"></span> <span class="ptxt">Gerät </span>online</span>
        <span v-else-if="online === false" class="gs-pill warn"><span class="dot"></span> offline</span>
        <span v-else class="gs-pill muted"><span class="dot"></span> verbinde …</span>
        <button class="gs-btn gs-ghost" @click="requestSync">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg><span class="btxt">Aktualisieren</span></button>
        <span class="gs-vdiv"></span>
        <button class="gs-btn gs-ghost" @click="showFeedback = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/></svg><span class="btxt">Feedback</span><span v-if="errorCount" class="gs-badge">{{ errorCount }}</span></button>
    </header>

    <div class="gs-main">
      <!-- Abdunklung: fängt den Klick daneben ab und schließt das Menü. -->
      <div v-if="navOffen" class="gs-navback" @click="navOffen = false"></div>
      <!-- Linke Modul-Navigation. Auf schmalen Schirmen ein ausklappbares Menü;
           ein Klick auf einen Eintrag schließt es wieder. -->
      <nav v-if="!loading && !bootError" id="gs-nav" class="gs-subnav"
           :class="{ offen: navOffen }" @click="navOffen = false">
          <div v-if="showLaeuten" class="lbl">Läuten</div>
          <button v-if="canView('steuerung')" :class="{ active: view === 'steuerung' }" @click="view = 'steuerung'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>Steuerung</button>
          <button v-if="canView('log')" :class="{ active: view === 'log' }" @click="view = 'log'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>Ereignis-Log<span v-if="logLines.length" class="cnt">{{ logLines.length }}</span></button>
          <div v-if="showEinstellungen" class="lbl">Einstellungen</div>
          <button v-if="canView('regeln')" :class="{ active: view === 'regeln' }" @click="view = 'regeln'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v3M16 3v3"/></svg>Automatik-Regeln<span v-if="rules.length" class="cnt">{{ rules.length }}</span></button>
          <button v-if="rights.manageExt" :class="{ active: view === 'geraet' }" @click="view = 'geraet'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 5V3m8 2V3M4 10h16"/></svg>Gerät</button>
          <button v-if="rights.manageExt" :class="{ active: view === 'email' }" @click="view = 'email'; loadEmail()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>E-Mail-Versand</button>

          <div class="gs-subfoot">
            <button class="ver" type="button" @click="openChangelog"
                    title="Was ist neu? Changelog anzeigen">v{{ APP_VERSION }}</button>
            <a v-if="updateAvailable" class="gs-update" :href="DOWNLOAD_URL" target="_blank" rel="noopener noreferrer"
               :title="`Version ${updateCheck!.latest} herunterladen und in ChurchTools hochladen`">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
              Version {{ updateCheck!.latest }} verfügbar
            </a>
            <div>Entwickelt mit <span class="heart">♥</span> von JosuaDev</div>
          </div>
        </nav>

      <main class="gs-content">
          <!-- Kompatibilitäts-Hinweis -->
          <div class="gs-compat">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>
            <span>Unterstützt aktuell <b>HEW VOCO-futura</b> (z.&nbsp;B. ST5). Weitere Systeme &amp; andere Hersteller folgen – eine <b>universelle</b> Lösung ist später geplant.</span>
          </div>

          <div v-if="bootError" class="gs-card"><div class="gs-body" style="color:var(--gs-danger)">Fehler beim Start: {{ bootError }}</div></div>

          <template v-else>
          <!-- ▸ Steuerung -->
          <template v-if="view === 'steuerung' && canView('steuerung')">
            <!-- Gateway weg? Dann laeutet nichts von allein - das muss man sehen. -->
            <div v-if="gatewayDown" class="gs-banner gw-down">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
              <div class="txt">
                <b>Gateway nicht erreichbar</b><br>
                <small>Es wird zurzeit <b>nicht automatisch geläutet</b>. Manuelles Läuten über die Knöpfe funktioniert weiterhin. {{ gatewayDownText }}</small>
              </div>
            </div>
            <div class="gs-banner" :class="simulate ? 'sim-on' : 'sim-off'">
              <span class="ic">
                <svg v-if="simulate" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.5 7.5 8 9 4.5-1.5 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>
                <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
              </span>
              <div class="txt">
                <b>{{ simulate ? 'Simulationsmodus aktiv' : 'SCHARF – echtes Läuten möglich' }}</b><br>
                <small>{{ simulate ? 'Es wird nichts an die Anlage gesendet. Du siehst nur, was passieren würde – und im Ereignis-Log die echten Antworten der Anlage.' : 'Knöpfe und Automatik lösen jetzt wirklich Läuten aus.' }}</small>
              </div>
              <label v-if="rights.manageExt" class="gs-switch"><button class="gs-toggle" :class="{ off: !simulate }" role="switch" :aria-checked="simulate" @click="setSimulate(!simulate)"></button> Simulation</label>
              <span v-else class="gs-switch" style="opacity:.75" title="Nur „Erweiterung verwalten“ kann den Sicherheitsmodus deaktivieren"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg> Simulation</span>
            </div>

            <!-- Aktuell läuft (aus stoppbaren Programmen – auch in Simulation echt) -->
            <section v-if="stoppable.length" class="gs-card">
              <div class="gs-head"><h2>Aktuell läuft</h2><span class="gs-spacer"></span><span class="gs-pill ok"><span class="dot"></span> {{ stoppable.length }} aktiv</span></div>
              <div class="gs-body">
                <div class="gs-list">
                  <div v-for="raw in stoppable" :key="raw" class="gs-row">
                    <span class="gs-ic" style="background:var(--gs-success-bg);color:var(--gs-green)"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg></span>
                    <div class="grow"><div class="name">{{ decodeName(raw) }}</div><div class="meta">{{ runningText(raw) }}</div></div>
                    <button class="gs-btn sm" :class="simulate ? 'gs-sim-btn' : 'gs-stop'" @click="stopProgram(raw)"><svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>{{ simulate ? 'Stop testen' : 'Stoppen' }}</button>
                  </div>
                </div>
              </div>
            </section>

            <section class="gs-card">
              <div class="gs-head"><h2>Programme</h2><span class="gs-spacer"></span>
                <span class="gs-pill blue">{{ simulate ? 'Simulation – „Testen"' : 'Scharf – „Läuten"' }}</span></div>
              <div class="gs-body">
                <div style="color:var(--gs-dim);font-size:14px;margin-bottom:6px">Gerät: <b style="color:var(--gs-text)">{{ device.serial || '(nicht konfiguriert)' }}</b></div>
                <p v-if="playable.length === 0" class="gs-empty">(keine startbaren Programme – Gerät online &amp; konfiguriert?)</p>
                <div v-else class="gs-list">
                  <div v-for="raw in playable" :key="raw" class="gs-row">
                    <span class="gs-ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg></span>
                    <div class="grow"><div class="name">{{ decodeName(raw) }}</div></div>
                    <label v-if="canEdit('steuerung')" class="gs-dur" title="Dauer für den „läuft“-Countdown">Dauer <input type="number" min="0" :value="durations[decodeName(raw)] ?? ''" @change="setDuration(decodeName(raw), Number(($event.target as HTMLInputElement).value))"> min</label>
                    <button class="gs-btn sm" :class="simulate ? 'gs-sim-btn' : 'gs-ring'" @click="fire(raw)">
                      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>{{ simulate ? 'Testen' : 'Läuten' }}</button>
                  </div>
                </div>
                <div v-if="playable.length" class="gs-foot">
                  <button class="gs-btn sm" :class="simulate ? 'gs-sim-btn' : 'gs-stop'" @click="stopAll">
                    <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>{{ simulate ? 'Stop testen' : 'Alles stoppen' }}</button>
                </div>
              </div>
            </section>

            <!-- Nächste automatische Läutungen (nur Anzeige, aus Regeln × Terminen) -->
            <section class="gs-card">
              <div class="gs-head"><h2>Nächste automatische Läutungen</h2><span class="gs-spacer"></span>
                <button class="gs-btn gs-ghost sm" @click="loadNextRingings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg><span class="btxt">Aktualisieren</span></button></div>
              <div class="gs-body">
                <p v-if="nextRingings.length === 0 && !ringingHint" class="gs-empty">(keine anstehenden Läutungen aus den Regeln in den nächsten 30 Tagen)</p>
                <p v-else-if="ringingHint" class="gs-readonly" style="margin-bottom:0">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
                  <span>{{ ringingHint }}</span></p>
                <div v-else class="gs-scroll">
                  <table>
                    <thead><tr><th>Wann</th><th>Programm</th><th>Ausgelöst durch</th></tr></thead>
                    <tbody>
                      <tr v-for="(n, i) in nextRingings" :key="i">
                        <td><b>{{ fmtDay(n.when) }} · {{ fmtTime(n.when) }}</b></td>
                        <td><span class="gs-label">{{ n.program }}</span></td>
                        <td class="gs-muted">{{ n.source }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p class="gs-note" style="color:var(--gs-dim)"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg><span>Vorschau aus ChurchTools (Zeit = Beginn − Vorlauf). Regeln <b>mit</b> Termin-Titel greifen nur bei Terminen, deren Titel <b>exakt</b> übereinstimmt – „Gottesdienst" trifft also nicht auch „Festgottesdienst". Regeln <b>ohne</b> Titel greifen bei allen Terminen des Kalenders. Das tatsächliche Auslösen übernimmt der Gateway-Dienst.</span></p>
              </div>
            </section>

            <!-- Ereignis-Log (abgespeckt) – voller Log unter „Ereignis-Log" -->
            <section v-if="steuerungLog.length" class="gs-card">
              <div class="gs-head"><h2>Letzte Ereignisse</h2><span class="gs-spacer"></span>
                <span class="gs-count">ℹ Info · ▶ Befehl · ◀ Läuten · ⚙ Simulation</span>
                <button v-if="canView('log')" class="gs-btn gs-ghost sm" style="margin-left:10px" @click="view = 'log'">Ganzes Log</button></div>
              <div class="gs-body">
                <div class="gs-log" style="max-height:160px">
                  <div v-for="(e, i) in steuerungLog.slice(0, 6)" :key="i"><span class="ts">{{ e.ts.toLocaleTimeString('de-DE') }}</span> <span :class="e.dir">{{ logIcon(e.dir) }}</span> {{ e.line }}</div>
                </div>
              </div>
            </section>
          </template>

          <!-- ▸ Ereignis-Log -->
          <section v-else-if="view === 'log' && canView('log')" class="gs-card">
            <div class="gs-head"><h2>Ereignis-Log</h2><span class="gs-spacer"></span>
              <span class="gs-count">ℹ Info · ▶ gesendet · ◀ Antwort · ⚙ Simulation</span>
              <button class="gs-btn gs-ghost sm" style="margin-left:10px" @click="logLines = []">Leeren</button></div>
            <div class="gs-body">
              <div class="gs-dltools">
                <label>Von <input type="datetime-local" v-model="dlFrom"></label>
                <label>Bis <input type="datetime-local" v-model="dlTo"></label>
                <button class="gs-btn gs-ghost sm" @click="downloadLog"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16"/></svg>Herunterladen</button>
                <span class="hint">leer = alles</span>
              </div>
              <div class="gs-log">
                <span v-if="logLines.length === 0" style="color:#7c8b99">(noch keine Ereignisse – „Aktualisieren" drücken oder Gerät verbinden)</span>
                <div v-for="(e, i) in logLines" :key="i"><span class="ts">{{ e.ts.toLocaleTimeString('de-DE') }}</span> <span :class="e.dir">{{ logIcon(e.dir) }}</span> {{ e.line }}</div>
              </div>
            </div>
          </section>

          <!-- ▸ Automatik-Regeln -->
          <section v-else-if="view === 'regeln' && canView('regeln')" class="gs-card">
            <div class="gs-head"><h2>Automatik-Regeln</h2><span class="gs-spacer"></span>
              <span v-if="!canEdit('regeln')" class="gs-pill muted">nur lesen</span>
              <button v-else class="gs-btn gs-ghost sm" @click="addRule"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Regel hinzufügen</button></div>
            <div class="gs-body">
              <p style="color:var(--gs-dim);font-size:13.5px;margin:0 0 14px">Vom Gateway-Dienst für automatisches Läuten genutzt (Termin → Programm). Der <b>Termin-Titel</b> muss <b>exakt</b> so lauten wie im Kalender – leer lassen heißt „jeder Termin des Kalenders".</p>
              <p v-if="!canEdit('regeln')" class="gs-readonly"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Zum Ändern brauchst du das Recht „Daten in Kategorie bearbeiten" für „Automatik-Regeln". Ein Admin vergibt es in der Rechteverwaltung unter „Glockensteuerung".</p>
              <p v-if="rules.length === 0" class="gs-empty">(noch keine Regeln)</p>
              <div v-for="(rule, i) in rules" :key="rule.id" class="gs-rule">
                <label>Name</label><input type="text" v-model="rule.name" :disabled="!canEdit('regeln')">
                <label>Kalender</label>
                <select :value="rule.calendarId ?? ''" :disabled="!canEdit('regeln')" @change="calId(rule, $event)">
                  <option value="">(jeder Kalender)</option>
                  <option v-for="c in calendars" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
                <label>Termin-Titel</label><input type="text" v-model="rule.title" placeholder="(egal) z. B. Gottesdienst" :disabled="!canEdit('regeln')">
                <label>Läuteprogramm</label>
                <select v-model="rule.pgsName" :disabled="!canEdit('regeln')">
                  <option value="">(bitte wählen)</option>
                  <optgroup v-if="catalog.sPGS.length" label="Sofort-PGS">
                    <option v-for="n in catalog.sPGS" :key="'s' + n" :value="n">{{ n }}</option>
                  </optgroup>
                  <optgroup v-if="catalog.melodies.length" label="Melodien">
                    <option v-for="n in catalog.melodies" :key="'m' + n" :value="n">{{ n }}</option>
                  </optgroup>
                  <optgroup v-if="catalog.programsteps.length" label="Programmschritte (Vorlagen)">
                    <option v-for="n in catalog.programsteps" :key="'p' + n" :value="n">{{ n }}</option>
                  </optgroup>
                  <option v-if="rule.pgsName && !allCatalogNames.includes(rule.pgsName)" :value="rule.pgsName">{{ rule.pgsName }} (aktuell)</option>
                </select>
                <label>Vorlauf (Min.)</label><input type="number" min="0" v-model.number="rule.leadMinutes" :disabled="!canEdit('regeln')">
                <label>Aktiv</label><label class="gs-switch"><input type="checkbox" v-model="rule.active" :disabled="!canEdit('regeln')"></label>
                <template v-if="canEdit('regeln')"><div></div><button class="gs-btn gs-stop sm" style="justify-self:start" @click="delRule(i)">Löschen</button></template>
              </div>
              <div v-if="canEdit('regeln')" class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveRules">Regeln speichern</button><span style="margin-left:10px;color:var(--gs-success-fg);font-weight:600;align-self:center">{{ saveMsg }}</span></div>
            </div>
          </section>

          <!-- ▸ Gerät -->
          <section v-else-if="view === 'geraet' && rights.manageExt" class="gs-card">
            <div class="gs-head"><h2>Gerät</h2></div>
            <div class="gs-body">
              <p class="gs-readonly"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg><span>Die Zugangsdaten gelten <b>global</b>: Sie liegen in der Kategorie „Steuerung", damit jede berechtigte Person (die Steuerung sehen darf) Status sehen und läuten kann. Konfigurieren darf nur, wer „Erweiterung verwalten" hat.</span></p>
              <div class="gs-fields">
                <label>Seriennummer</label><input type="text" v-model="device.serial" placeholder="VH-XXXXXX">
                <label>Geräte-Passwort</label><input type="password" v-model="device.devicePw" placeholder="geheim">
                <label>Broker-URL</label><input type="text" v-model="device.brokerUrl">
              </div>
              <p class="gs-note"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Seriennummer + Passwort erlauben das Läuten – Modulzugriff einschränken. Verbinden &amp; Status lesen ist ungefährlich.</p>
              <div class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveDevice">Gerät speichern &amp; verbinden</button></div>
            </div>
          </section>

          <!-- ▸ E-Mail-Versand -->
          <section v-else-if="view === 'email' && rights.manageExt" class="gs-card">
            <div class="gs-head"><h2>E-Mail-Versand</h2></div>
            <div class="gs-body">
              <p class="gs-readonly"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg><span>Verschickt wird vom <b>Gateway-Dienst</b>, nicht aus dem Browser: Eine Webseite kann kein SMTP sprechen. Die Extension stellt Nachrichten nur ein – der Dienst holt sie binnen einer Minute ab. Läuft er nicht, geht nichts raus.</span></p>

              <div class="gs-fields">
                <label>Postausgang (Server)</label><input type="text" v-model="email.host" placeholder="smtp.example.de">
                <label>Port</label><input type="number" v-model.number="email.port" min="1" max="65535">
                <label>Verschlüsselung</label>
                <select v-model="email.security">
                  <option value="starttls">STARTTLS (üblich, Port 587)</option>
                  <option value="ssl">SSL/TLS (Port 465)</option>
                </select>
                <label>Benutzername</label><input type="text" v-model="email.user" placeholder="postausgang@example.de" autocomplete="off">
                <label>Passwort</label><input type="password" v-model="email.password" placeholder="geheim" autocomplete="new-password">
                <label>Absender</label><input type="email" v-model="email.from" placeholder="(wie Benutzername)">
                <label>Empfänger</label><input type="email" v-model="email.to" placeholder="wer die Nachrichten bekommt">
              </div>

              <p style="color:var(--gs-dim);font-size:13.5px;margin:18px 0 8px"><b>Wann verschickt wird</b></p>
              <label class="gs-switch" style="display:flex;gap:9px;margin-bottom:8px">
                <button class="gs-toggle" :class="{ off: !email.sendFeedback }" @click="email.sendFeedback = !email.sendFeedback"></button>
                <span>Feedback-Formular per E-Mail senden <small style="color:var(--gs-faint);font-weight:400">– sonst öffnet sich das E-Mail-Programm</small></span>
              </label>
              <label class="gs-switch" style="display:flex;gap:9px">
                <button class="gs-toggle" :class="{ off: !email.sendErrors }" @click="email.sendErrors = !email.sendErrors"></button>
                <span>Störungen und Fehler melden</span>
              </label>

              <p class="gs-note"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg><span>Das Passwort liegt in der eigenen Kategorie <b>„E-Mail-Versand"</b> – <b>nicht</b> in „Steuerung", die jeder mit Modulzugriff lesen darf. Bitte in der Rechteverwaltung prüfen, dass nur Verwalter Leserechte darauf haben.</span></p>

              <div class="gs-foot" style="justify-content:flex-start;gap:10px">
                <button class="gs-btn gs-primary" @click="saveEmail">Speichern</button>
                <button class="gs-btn gs-ghost" @click="testMail" :disabled="!email.host">Testnachricht senden</button>
              </div>
            </div>
          </section>

          <!-- ▸ Kein Bereich freigegeben -->
          <section v-else class="gs-card">
            <div class="gs-body gs-empty">Für dieses Modul sind dir noch keine Bereiche freigegeben. Ein Admin kann dir in der Rechteverwaltung unter „Glockensteuerung" Rechte geben (sehen/bearbeiten je Kategorie). Über „Feedback senden" kannst du dich melden.</div>
          </section>
          </template>
      </main>
    </div>
    </template>

    <!-- Feedback modal -->
    <!-- Changelog: „Was ist neu?" – geoeffnet ueber die Versionsnummer unten links.
         Bewusst ohne v-html: Der Text kommt zwar aus dem eigenen Release, wird
         aber als Daten gerendert, nicht als Markup (siehe update.ts). -->
    <div v-if="showChangelog" class="gs-backdrop" @click.self="showChangelog = false">
      <div class="gs-modal gs-cl-modal" role="dialog" aria-modal="true" aria-label="Was ist neu">
        <h3>Was ist neu?</h3>
        <p class="hint">Installiert ist Version {{ APP_VERSION }}.<span v-if="updateAvailable"> Verfügbar ist {{ updateCheck!.latest }}.</span></p>

        <div v-if="changelogLaedt" class="gs-cl-info">Changelog wird geladen …</div>
        <div v-else-if="!changelog.length" class="gs-cl-info">
          Der Changelog konnte nicht abgerufen werden. Er steht bei den
          <a :href="RELEASES_URL" target="_blank" rel="noopener noreferrer">Releases auf GitHub</a>.
        </div>
        <div v-else class="gs-cl">
          <template v-for="(z, i) in changelog" :key="i">
            <h4 v-if="z.art === 'version'" class="v">{{ z.text }}</h4>
            <div v-else-if="z.art === 'gruppe'" class="g">{{ z.text }}</div>
            <div v-else-if="z.art === 'bereich'" class="b">{{ z.text }}</div>
            <div v-else-if="z.art === 'eintrag'" class="e">{{ z.text }}</div>
            <p v-else class="t">{{ z.text }}</p>
          </template>
        </div>

        <div class="actions">
          <a v-if="updateAvailable" class="gs-btn gs-primary" :href="DOWNLOAD_URL" target="_blank" rel="noopener noreferrer">
            Version {{ updateCheck!.latest }} herunterladen</a>
          <button class="gs-btn gs-ghost" @click="showChangelog = false">Schließen</button>
        </div>
      </div>
    </div>

    <div v-if="showFeedback" class="gs-backdrop" @click.self="showFeedback = false">
      <div class="gs-modal" role="dialog" aria-modal="true" aria-label="Feedback">
        <h3>Feedback senden</h3>
        <p class="hint">Geht direkt an die Entwicklung. Technische Angaben (Instanz, Version, letzte Ereignisse) werden angehängt – <b>keine</b> Passwörter.</p>
        <div class="field"><label>Name (optional)</label><input type="text" v-model="fb.name" placeholder="Dein Name"></div>
        <div class="field"><label>E-Mail für Rückfragen (optional)</label><input type="email" v-model="fb.email" placeholder="du@gemeinde.de"></div>
        <div class="field"><label>Art</label><select v-model="fb.category"><option>Fehler / etwas funktioniert nicht</option><option>Verbesserungsvorschlag</option><option>Frage</option><option>Sonstiges</option></select></div>
        <div class="field"><label>Nachricht</label><textarea rows="4" v-model="fb.message" placeholder="Was ist passiert / was wünschst du dir?"></textarea></div>
        <div class="actions"><button class="gs-btn gs-ghost" @click="showFeedback = false">Abbrechen</button><button class="gs-btn gs-primary" @click="sendFeedback">Senden</button></div>
      </div>
    </div>

    <div class="gs-toast" :class="{ show: toastMsg }">{{ toastMsg }}</div>
  </div>
</template>
