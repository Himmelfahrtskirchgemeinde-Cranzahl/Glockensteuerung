<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { churchtoolsClient } from '@churchtools/churchtools-client';
import { ConfigStore, newRule } from './config';
import type { DeviceConfig, MappingRule } from './config';
import { VocoMqtt, decodeName } from './voco/mqtt';
import { reportError, submitFeedback, maskSerial, APP_VERSION, FEEDBACK_URL } from './feedback';
import type { ReportContext, FeedbackFields } from './feedback';

const isDev = import.meta.env.MODE === 'development';
declare const window: Window & typeof globalThis & { settings?: { base_url?: string } };
const baseUrl = window.settings?.base_url ?? import.meta.env.VITE_BASE_URL;

const store = new ConfigStore();
let voco: VocoMqtt | undefined;

const simulate = ref(true);
const online = ref<boolean | null>(null);
const playable = ref<string[]>([]);
const device = ref<DeviceConfig>({ serial: '', devicePw: '', brokerUrl: 'wss://hew-voco.de:8084/mqtt' });
const rules = ref<MappingRule[]>([]);
const calendars = ref<{ id: number; name: string }[]>([]);
type LogEntry = { t: string; dir: 'in' | 'out' | 'sim'; line: string };
const logLines = ref<LogEntry[]>([]);
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
        logTail: logLines.value.slice(0, 15).map((e) => `${e.t} ${e.dir} ${e.line}`),
    };
}

function pushLog(line: string, dir: 'in' | 'out' | 'sim') {
    logLines.value.unshift({ t: new Date().toLocaleTimeString('de-DE'), dir, line });
    if (logLines.value.length > 80) logLines.value.pop();
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

onMounted(() => {
    window.addEventListener('error', (e) => handleError('window.onerror', e.error ?? e.message));
    window.addEventListener('unhandledrejection', (e) => handleError('promise', (e as PromiseRejectionEvent).reason));
    boot();
});

async function boot() {
    try {
        if (isDev && import.meta.env.VITE_USERNAME) {
            await churchtoolsClient.post('/login', {
                username: import.meta.env.VITE_USERNAME,
                password: import.meta.env.VITE_PASSWORD,
            });
        }
        await store.init(isDev);
        const cfg = await store.load();
        if (cfg.device) device.value = { brokerUrl: 'wss://hew-voco.de:8084/mqtt', ...cfg.device };
        rules.value = cfg.rules;
        try { calendars.value = await churchtoolsClient.get<{ id: number; name: string }[]>('/calendars'); } catch { calendars.value = []; }
        if (device.value.serial && device.value.devicePw) connectVoco();
        loading.value = false;
    } catch (e) {
        loading.value = false;
        bootError.value = String(e);
        handleError('boot', e);
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
    if (!on && !confirm('Simulation ausschalten?\n\nDanach lösen Knöpfe und Automatik ECHTES Läuten aus.')) return;
    simulate.value = on;
    if (voco) voco.simulate = on;
    pushLog(on ? 'Simulation EIN – es wird nichts gesendet.' : 'Simulation AUS – Befehle werden real gesendet!', 'sim');
}

function requestSync() { voco?.requestSync(); }
function stopAll() {
    if (simulate.value) { voco?.stopAll(); toast('Simulation: nichts gesendet.'); }
    else if (confirm('Wirklich ALLES stoppen?')) voco?.stopAll();
}

async function saveDevice() {
    try {
        await store.saveDevice(device.value);
        connectVoco();
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
    <div class="gs-wrap">
      <h1 class="gs-title"><span class="gs-bell">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>
      </span> Glockensteuerung</h1>
      <p class="gs-sub">Läuteprogramme aus dem ChurchTools-Kalender auslösen — HEW VOCO-futura ST5.</p>

      <p v-if="loading">Lade …</p>
      <div v-else-if="bootError" class="gs-card" style="color:var(--gs-danger);padding:16px 18px">Fehler beim Start: {{ bootError }}</div>

      <template v-else>
        <!-- Simulations-Banner -->
        <div class="gs-banner" :class="simulate ? 'sim-on' : 'sim-off'">
          <span class="ic">
            <svg v-if="simulate" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.5 7.5 8 9 4.5-1.5 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
          </span>
          <div class="txt">
            <b>{{ simulate ? 'Simulationsmodus aktiv' : 'SCHARF – echtes Läuten möglich' }}</b><br>
            <small>{{ simulate ? 'Es wird nichts an die Anlage gesendet. Du siehst nur, was passieren würde – und im Log die Antworten der Anlage.' : 'Knöpfe und Automatik lösen jetzt wirklich Läuten aus.' }}</small>
          </div>
          <label class="gs-switch"><button class="gs-toggle" :class="{ off: !simulate }" role="switch" :aria-checked="simulate" @click="setSimulate(!simulate)"></button> Simulation</label>
        </div>

        <!-- Status / Programme -->
        <section class="gs-card">
          <div class="gs-head"><h2>Status</h2><span class="gs-spacer"></span>
            <span v-if="online === null" class="gs-pill muted"><span class="dot"></span> verbinde …</span>
            <span v-else-if="online" class="gs-pill ok"><span class="dot"></span> online</span>
            <span v-else class="gs-pill warn"><span class="dot"></span> offline</span>
            <button class="gs-btn gs-ghost" style="margin-left:10px" @click="requestSync">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>Aktualisieren</button>
          </div>
          <div style="color:var(--gs-dim);font-size:14px;padding:14px 18px 0">Gerät: <b style="color:var(--gs-text)">{{ device.serial || '(nicht konfiguriert)' }}</b></div>
          <div style="font-weight:700;font-size:13px;color:var(--gs-dim);padding:10px 18px 0">Programme {{ simulate ? 'testen' : 'auslösen' }}</div>
          <p v-if="playable.length === 0" class="gs-empty">(keine startbaren Programme – Gerät online &amp; konfiguriert?)</p>
          <div v-else class="gs-list">
            <div v-for="raw in playable" :key="raw" class="gs-row">
              <span class="gs-ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg></span>
              <div class="grow"><div class="name">{{ decodeName(raw) }}</div></div>
              <button class="gs-btn" :class="simulate ? 'gs-sim-btn' : 'gs-ring'" @click="fire(raw)">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>{{ simulate ? 'Testen' : 'Läuten' }}</button>
            </div>
          </div>
          <div v-if="playable.length" class="gs-foot">
            <button class="gs-btn" :class="simulate ? 'gs-sim-btn' : 'gs-stop'" @click="stopAll">
              <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>{{ simulate ? 'Stop testen' : 'Alles stoppen' }}</button>
          </div>
        </section>

        <!-- Ereignis-Log -->
        <section class="gs-card">
          <div class="gs-head"><h2>Ereignis-Log</h2><span class="gs-count">◀ Antwort · ▶ gesendet · ⚙ Simulation</span><span class="gs-spacer"></span>
            <button class="gs-btn gs-ghost" @click="logLines = []">Leeren</button></div>
          <div class="gs-log">
            <span v-if="logLines.length === 0" style="color:#7c8b99">(noch keine Ereignisse – „Aktualisieren" drücken oder Gerät verbinden)</span>
            <div v-for="(e, i) in logLines" :key="i"><span class="ts">{{ e.t }}</span> <span :class="e.dir">{{ logIcon(e.dir) }}</span> {{ e.line }}</div>
          </div>
        </section>

        <!-- Gerät -->
        <section class="gs-card">
          <div class="gs-head"><h2>Gerät</h2></div>
          <div class="gs-fields">
            <label>Seriennummer</label><input type="text" v-model="device.serial" placeholder="VH-XXXXXX">
            <label>Geräte-Passwort</label><input type="password" v-model="device.devicePw" placeholder="geheim">
            <label>Broker-URL</label><input type="text" v-model="device.brokerUrl">
          </div>
          <p class="gs-note"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Seriennummer + Passwort erlauben das Läuten – Modulzugriff einschränken. Verbinden &amp; Status lesen ist ungefährlich.</p>
          <div class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveDevice">Gerät speichern &amp; verbinden</button></div>
        </section>

        <!-- Automatik-Regeln -->
        <section class="gs-card">
          <div class="gs-head"><h2>Automatik-Regeln</h2><span class="gs-spacer"></span>
            <button class="gs-btn gs-ghost" @click="addRule"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Regel hinzufügen</button></div>
          <p style="color:var(--gs-dim);font-size:13.5px;padding:14px 18px 0;margin:0">Vom Gateway-Dienst für automatisches Läuten genutzt (Termin → Programm).</p>
          <div id="rules">
            <p v-if="rules.length === 0" class="gs-empty" style="padding-left:0">(noch keine Regeln)</p>
            <div v-for="(rule, i) in rules" :key="rule.id" style="border:1px solid var(--gs-border);border-radius:var(--gs-radius-sm);padding:12px;margin-bottom:10px;display:grid;grid-template-columns:150px 1fr;gap:9px 12px;align-items:center">
              <label style="color:var(--gs-dim);font-size:14px">Name</label><input type="text" v-model="rule.name">
              <label style="color:var(--gs-dim);font-size:14px">Kalender</label>
              <select :value="rule.calendarId ?? ''" @change="calId(rule, $event)">
                <option value="">(jeder Kalender)</option>
                <option v-for="c in calendars" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
              <label style="color:var(--gs-dim);font-size:14px">Veranstaltungsart</label><input type="text" v-model="rule.category" placeholder="(egal) z. B. Gottesdienst">
              <label style="color:var(--gs-dim);font-size:14px">Läuteprogramm</label>
              <input type="text" v-model="rule.pgsName" :list="'pgs-' + i" placeholder="Name des Sofort-PGS">
              <datalist :id="'pgs-' + i"><option v-for="raw in playable" :key="raw" :value="decodeName(raw)"></option></datalist>
              <label style="color:var(--gs-dim);font-size:14px">Vorlauf (Min.)</label><input type="number" min="0" v-model.number="rule.leadMinutes">
              <label style="color:var(--gs-dim);font-size:14px">Aktiv</label><label class="gs-switch"><input type="checkbox" v-model="rule.active"></label>
              <div></div><button class="gs-btn gs-stop" style="justify-self:start;padding:6px 12px" @click="delRule(i)">Löschen</button>
            </div>
          </div>
          <div class="gs-foot" style="justify-content:flex-start"><button class="gs-btn gs-primary" @click="saveRules">Regeln speichern</button><span style="margin-left:10px;color:var(--gs-success-fg);font-weight:600;align-self:center">{{ saveMsg }}</span></div>
        </section>
      </template>
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
