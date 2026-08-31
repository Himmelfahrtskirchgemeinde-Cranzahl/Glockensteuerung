<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { churchtoolsClient } from '@churchtools/churchtools-client';
import { ConfigStore, newRule } from './config';
import type { CatKey, DeviceConfig, MappingRule } from './config';
import { VocoMqtt, decodeName } from './voco/mqtt';
import { reportError, submitFeedback, maskSerial, APP_VERSION, FEEDBACK_URL } from './feedback';
import type { ReportContext, FeedbackFields } from './feedback';
import { loadRights } from './perms';
import type { Rights } from './perms';

const isDev = import.meta.env.MODE === 'development';
declare const window: Window & typeof globalThis & { settings?: { base_url?: string } };
const baseUrl = window.settings?.base_url ?? import.meta.env.VITE_BASE_URL;

const store = new ConfigStore();
let voco: VocoMqtt | undefined;

type View = 'steuerung' | 'log' | 'regeln' | 'geraet';
const view = ref<View>('steuerung');

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
const showEinstellungen = computed(() => canView('regeln') || canView('geraet'));
const simulate = ref(true);
const online = ref<boolean | null>(null);
const playable = ref<string[]>([]);
const stoppable = ref<string[]>([]);          // laufende (= stoppbare) Programme
const runningSince = ref<Record<string, number>>({}); // roher Name -> Startzeit (ms)
const durations = ref<Record<string, number>>({});    // Anzeigename -> Minuten
const now = ref<number>(Date.now());
let clockTimer: number | undefined;
const device = ref<DeviceConfig>({ serial: '', devicePw: '', brokerUrl: 'wss://hew-voco.de:8084/mqtt' });
const rules = ref<MappingRule[]>([]);
const calendars = ref<{ id: number; name: string }[]>([]);
type LogEntry = { ts: Date; dir: 'in' | 'out' | 'sim'; line: string };
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

function pushLog(line: string, dir: 'in' | 'out' | 'sim') {
    logLines.value.unshift({ ts: new Date(), dir, line });
    if (logLines.value.length > 500) logLines.value.pop();
}

async function handleError(where: string, err: unknown) {
    pushLog('Fehler: ' + (err instanceof Error ? err.message : String(err)), 'in');
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
    voco?.disconnect();
});

async function boot() {
    try {
        if (isDev && import.meta.env.VITE_USERNAME) {
            await churchtoolsClient.post('/login', {
                username: import.meta.env.VITE_USERNAME,
                password: import.meta.env.VITE_PASSWORD,
            });
        }
        await store.init();
        catIds.value = { ...store.catIds };
        rights.value = await loadRights();
        pickDefaultView();
        const cfg = await store.load();
        if (cfg.device) device.value = { brokerUrl: 'wss://hew-voco.de:8084/mqtt', ...cfg.device };
        rules.value = cfg.rules;
        durations.value = cfg.durations ?? {};
        // Gemerkter Status gilt nur für Berechtigte; alle anderen bleiben in Simulation.
        simulate.value = rights.value.manageExt ? (cfg.simulate ?? true) : true;
        try { calendars.value = await churchtoolsClient.get<{ id: number; name: string }[]>('/calendars'); } catch { calendars.value = []; }
        if (device.value.serial && device.value.devicePw) connectVoco();
        loading.value = false;
    } catch (e) {
        loading.value = false;
        bootError.value = describeError(e);
        handleError('boot', e);
    }
}

function pickDefaultView() {
    const order: View[] = ['steuerung', 'log', 'regeln', 'geraet'];
    if (!canView(view.value)) {
        const first = order.find((v) => canView(v));
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
    };
    pushLog('Verbinde mit Broker …', 'out');
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
        setTimeout(() => (saveMsg.value = ''), 2500);
    } catch (e) { handleError('saveRules', e); }
}

function calId(rule: MappingRule, ev: Event) {
    const v = (ev.target as HTMLSelectElement).value;
    rule.calendarId = v ? Number(v) : null;
}

async function sendFeedback() {
    if (!fb.value.message.trim()) { toast('Bitte eine Nachricht eingeben.'); return; }
    const res = await submitFeedback(fb.value, ctx());
    showFeedback.value = false;
    fb.value = { name: '', email: '', category: 'Fehler / etwas funktioniert nicht', message: '' };
    if (res.sent) toast('Danke! Feedback wurde gesendet.');
    else if (res.mailto) { toast('E-Mail-Programm wird geöffnet …'); window.location.href = res.mailto; }
    else toast('Konnte nicht senden.');
}

const logIcon = (d: string) => (d === 'in' ? '◀' : d === 'sim' ? '⚙' : '▶');
</script>

<template>
  <div class="gs">
    <!-- Kopfleiste (voll breit, fix) -->
    <header class="gs-mhead">
        <span class="mi">
          <svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>
        </span>
        <h1>Glockensteuerung</h1>
        <span class="sp"></span>
        <span v-if="!loading && !bootError" class="gs-pill" :class="simulate ? 'blue' : 'warn'">
          {{ simulate ? 'Simulation' : 'SCHARF' }}
        </span>
        <span v-if="online === true" class="gs-pill ok"><span class="dot"></span> Gerät online</span>
        <span v-else-if="online === false" class="gs-pill warn"><span class="dot"></span> offline</span>
        <span v-else class="gs-pill muted"><span class="dot"></span> verbinde …</span>
        <button class="gs-btn gs-ghost" @click="requestSync">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>Aktualisieren</button>
    </header>

    <div class="gs-main">
      <!-- Linke Modul-Navigation (durchgehend) -->
      <nav v-if="!loading && !bootError" class="gs-subnav">
          <div v-if="showLaeuten" class="lbl">Läuten</div>
          <button v-if="canView('steuerung')" :class="{ active: view === 'steuerung' }" @click="view = 'steuerung'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>Steuerung</button>
          <button v-if="canView('log')" :class="{ active: view === 'log' }" @click="view = 'log'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>Ereignis-Log<span v-if="logLines.length" class="cnt">{{ logLines.length }}</span></button>
          <div v-if="showEinstellungen" class="lbl">Einstellungen</div>
          <button v-if="canView('regeln')" :class="{ active: view === 'regeln' }" @click="view = 'regeln'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v3M16 3v3"/></svg>Automatik-Regeln<span v-if="rules.length" class="cnt">{{ rules.length }}</span></button>
          <button v-if="canView('geraet')" :class="{ active: view === 'geraet' }" @click="view = 'geraet'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 5V3m8 2V3M4 10h16"/></svg>Gerät</button>
          <div class="lbl">Hilfe</div>
          <button @click="showFeedback = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/></svg>Feedback senden</button>
        </nav>

      <main class="gs-content">
          <!-- Kompatibilitäts-Hinweis -->
          <div class="gs-compat">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>
            <span>Unterstützt aktuell <b>HEW VOCO-futura</b> (z.&nbsp;B. ST5). Weitere Systeme &amp; andere Hersteller folgen – eine <b>universelle</b> Lösung ist später geplant.</span>
          </div>

          <p v-if="loading">Lade …</p>
          <div v-else-if="bootError" class="gs-card"><div class="gs-body" style="color:var(--gs-danger)">Fehler beim Start: {{ bootError }}</div></div>

          <template v-else>
          <!-- ▸ Steuerung -->
          <template v-if="view === 'steuerung' && canView('steuerung')">
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
          </template>

          <!-- ▸ Ereignis-Log -->
          <section v-else-if="view === 'log' && canView('log')" class="gs-card">
            <div class="gs-head"><h2>Ereignis-Log</h2><span class="gs-spacer"></span>
              <span class="gs-count">◀ Antwort · ▶ gesendet · ⚙ Simulation</span>
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
              <p style="color:var(--gs-dim);font-size:13.5px;margin:0 0 14px">Vom Gateway-Dienst für automatisches Läuten genutzt (Termin → Programm).</p>
              <p v-if="!canEdit('regeln')" class="gs-readonly"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Zum Ändern brauchst du das Recht „Daten in Kategorie bearbeiten" für „Automatik-Regeln". Ein Admin vergibt es in der Rechteverwaltung unter „Glockensteuerung".</p>
              <p v-if="rules.length === 0" class="gs-empty">(noch keine Regeln)</p>
              <div v-for="(rule, i) in rules" :key="rule.id" class="gs-rule">
                <label>Name</label><input type="text" v-model="rule.name" :disabled="!canEdit('regeln')">
                <label>Kalender</label>
                <select :value="rule.calendarId ?? ''" :disabled="!canEdit('regeln')" @change="calId(rule, $event)">
                  <option value="">(jeder Kalender)</option>
                  <option v-for="c in calendars" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
                <label>Veranstaltungsart</label><input type="text" v-model="rule.category" placeholder="(egal) z. B. Gottesdienst" :disabled="!canEdit('regeln')">
                <label>Läuteprogramm</label>
                <input type="text" v-model="rule.pgsName" :list="'pgs-' + i" placeholder="Name des Sofort-PGS" :disabled="!canEdit('regeln')">
                <datalist :id="'pgs-' + i"><option v-for="raw in playable" :key="raw" :value="decodeName(raw)"></option></datalist>
                <label>Vorlauf (Min.)</label><input type="number" min="0" v-model.number="rule.leadMinutes" :disabled="!canEdit('regeln')">
                <label>Aktiv</label><label class="gs-switch"><input type="checkbox" v-model="rule.active" :disabled="!canEdit('regeln')"></label>
                <template v-if="canEdit('regeln')"><div></div><button class="gs-btn gs-stop sm" style="justify-self:start" @click="delRule(i)">Löschen</button></template>
              </div>
              <div v-if="canEdit('regeln')" class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveRules">Regeln speichern</button><span style="margin-left:10px;color:var(--gs-success-fg);font-weight:600;align-self:center">{{ saveMsg }}</span></div>
            </div>
          </section>

          <!-- ▸ Gerät -->
          <section v-else-if="view === 'geraet' && canView('geraet')" class="gs-card">
            <div class="gs-head"><h2>Gerät</h2><span class="gs-spacer"></span><span v-if="!canEdit('geraet')" class="gs-pill muted">nur lesen</span></div>
            <div class="gs-body">
              <p v-if="!canEdit('geraet')" class="gs-readonly"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Zum Ändern brauchst du das Recht „Daten in Kategorie bearbeiten" für „Gerät". Ein Admin vergibt es in der Rechteverwaltung unter „Glockensteuerung".</p>
              <div class="gs-fields">
                <label>Seriennummer</label><input type="text" v-model="device.serial" placeholder="VH-XXXXXX" :disabled="!canEdit('geraet')">
                <label>Geräte-Passwort</label><input type="password" v-model="device.devicePw" placeholder="geheim" :disabled="!canEdit('geraet')">
                <label>Broker-URL</label><input type="text" v-model="device.brokerUrl" :disabled="!canEdit('geraet')">
              </div>
              <p class="gs-note"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Seriennummer + Passwort erlauben das Läuten – Modulzugriff einschränken. Verbinden &amp; Status lesen ist ungefährlich.</p>
              <div v-if="canEdit('geraet')" class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveDevice">Gerät speichern &amp; verbinden</button></div>
            </div>
          </section>

          <!-- ▸ Kein Bereich freigegeben -->
          <section v-else class="gs-card">
            <div class="gs-body gs-empty">Für dieses Modul sind dir noch keine Bereiche freigegeben. Ein Admin kann dir in der Rechteverwaltung unter „Glockensteuerung" Rechte geben (sehen/bearbeiten je Kategorie). Über „Feedback senden" kannst du dich melden.</div>
          </section>
          </template>
      </main>
    </div>

    <!-- Feedback FAB -->
    <button class="gs-fab" @click="showFeedback = true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/></svg>Feedback<span v-if="errorCount" class="badge">{{ errorCount }}</span>
    </button>

    <!-- Feedback modal -->
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
