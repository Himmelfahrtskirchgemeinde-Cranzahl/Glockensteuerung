import './app.css';
import { churchtoolsClient } from '@churchtools/churchtools-client';
import { ConfigStore, newRule, type AppConfig, type DeviceConfig, type MappingRule } from './config';
import { VocoMqtt, decodeName } from './voco/mqtt';
import {
    reportError, submitFeedback, maskSerial, APP_VERSION, FEEDBACK_URL,
    type ReportContext, type FeedbackFields,
} from './feedback';

if (import.meta.env.MODE === 'development') {
    import('./utils/reset.css');
}

declare const window: Window & typeof globalThis & { settings?: { base_url?: string } };

const isDev = import.meta.env.MODE === 'development';
const baseUrl = window.settings?.base_url ?? import.meta.env.VITE_BASE_URL;
churchtoolsClient.setBaseUrl(baseUrl);

const app = document.querySelector<HTMLDivElement>('#app')!;
const store = new ConfigStore();
let cfg: AppConfig = { device: null, rules: [] };
let voco: VocoMqtt | undefined;
let calendars: { id: number; name: string }[] = [];

let simulate = true; // Sicherheit: beim Öffnen immer an
let errorCount = 0;
type LogEntry = { t: string; dir: 'in' | 'out' | 'sim'; line: string };
let logLines: LogEntry[] = [];

const bell = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v2M5 10a7 7 0 0 1 14 0c0 5 2 6 2 6H3s2-1 2-6Z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>`;
const esc = (s: string) => (s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));

function ctx(): ReportContext {
    let instance = '';
    try { instance = new URL(baseUrl).host; } catch { instance = String(baseUrl); }
    return {
        version: APP_VERSION,
        instance,
        device: maskSerial(cfg.device?.serial),
        online: voco?.status.online ?? null,
        userAgent: navigator.userAgent,
        logTail: logLines.slice(0, 15).map((e) => `${e.t} ${e.dir} ${e.line}`),
    };
}

function pushLog(line: string, dir: 'in' | 'out' | 'sim') {
    logLines.unshift({ t: new Date().toLocaleTimeString('de-DE'), dir, line });
    if (logLines.length > 80) logLines.pop();
    updateLogEl();
}

async function handleError(where: string, err: unknown) {
    pushLog('Fehler: ' + (err instanceof Error ? err.message : String(err)), 'in');
    const sent = await reportError(where, err, ctx());
    if (!sent && !FEEDBACK_URL) { errorCount++; updateFab(); }
}

async function boot() {
    window.addEventListener('error', (e) => handleError('window.onerror', e.error ?? e.message));
    window.addEventListener('unhandledrejection', (e) => handleError('promise', e.reason));
    app.innerHTML = `<div class="gs"><div class="gs-wrap"><p>Lade …</p></div></div>`;
    try {
        if (isDev && import.meta.env.VITE_USERNAME) {
            await churchtoolsClient.post('/login', {
                username: import.meta.env.VITE_USERNAME,
                password: import.meta.env.VITE_PASSWORD,
            });
        }
        await store.init(isDev);
        cfg = await store.load();
        try { calendars = await churchtoolsClient.get('/calendars'); } catch { calendars = []; }
        if (cfg.device?.serial && cfg.device?.devicePw) connectVoco();
        render();
    } catch (e) {
        handleError('boot', e);
        app.innerHTML = `<div class="gs"><div class="gs-wrap"><div class="gs-card" style="color:var(--gs-danger)">Fehler beim Start: ${esc(String(e))}</div></div></div>`;
    }
}

function connectVoco() {
    if (!cfg.device) return;
    voco?.disconnect();
    voco = new VocoMqtt(cfg.device);
    voco.simulate = simulate;
    voco.onUpdate = render;
    voco.onLog = pushLog;
    pushLog('Verbinde mit Broker …', 'out');
    voco.connect().catch((e) => handleError('mqtt.connect', e));
}

function fire(nameRaw: string) {
    if (!voco) return;
    if (simulate) { voco.start(nameRaw); toast('Simulation: nichts gesendet – nur protokolliert.'); return; }
    if (confirm(`SCHARF: Programm wirklich AUSLÖSEN?\n\n${decodeName(nameRaw)}\n\nDas löst echtes Läuten aus.`)) {
        voco.start(nameRaw); toast('Befehl gesendet.');
    }
}

function setSimulate(on: boolean) {
    if (!on && !confirm('Simulation ausschalten?\n\nDanach lösen Knöpfe und Automatik ECHTES Läuten aus.')) { render(); return; }
    simulate = on;
    if (voco) voco.simulate = on;
    pushLog(on ? 'Simulation EIN – es wird nichts gesendet.' : 'Simulation AUS – Befehle werden real gesendet!', 'sim');
    render();
}

/* ---------------- Rendering ---------------- */
function render() {
    const d = cfg.device;
    const online = voco?.status.online;
    const playable = voco?.status.playable ?? [];
    const onlinePill = online == null
        ? `<span class="gs-pill muted"><span class="dot"></span> verbinde …</span>`
        : online ? `<span class="gs-pill ok"><span class="dot"></span> online</span>`
                 : `<span class="gs-pill warn"><span class="dot"></span> offline</span>`;

    app.innerHTML = `
    <div class="gs">
      <div class="gs-wrap">
        <h1 class="gs-title"><span class="gs-bell">${bell}</span> Glockensteuerung</h1>
        <p class="gs-sub">Läuteprogramme aus dem ChurchTools-Kalender auslösen — HEW VOCO-futura ST5.</p>

        <div class="gs-banner ${simulate ? 'sim-on' : 'sim-off'}">
          <span class="ic">${simulate
            ? `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.5 7.5 8 9 4.5-1.5 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>`
            : `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>`}</span>
          <div class="txt"><b>${simulate ? 'Simulationsmodus aktiv' : 'SCHARF – echtes Läuten möglich'}</b><br>
            <small>${simulate ? 'Es wird nichts an die Anlage gesendet. Du siehst nur, was passieren würde – und im Log die Antworten der Anlage.' : 'Knöpfe und Automatik lösen jetzt wirklich Läuten aus.'}</small></div>
          <label class="gs-switch"><button class="gs-toggle ${simulate ? '' : 'off'}" id="sim-toggle" role="switch" aria-checked="${simulate}"></button> Simulation</label>
        </div>

        <section class="gs-card">
          <div class="gs-head"><h2>Status</h2><span class="gs-spacer"></span>${onlinePill}
            <button class="gs-btn gs-ghost" id="refresh" style="margin-left:10px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>Aktualisieren</button></div>
          <div style="color:var(--gs-dim);font-size:14px;margin:-4px 0 12px">Gerät: <b style="color:var(--gs-text)">${d?.serial ? esc(d.serial) : '(nicht konfiguriert)'}</b></div>
          <div style="font-weight:700;font-size:13px;color:var(--gs-dim);margin-bottom:6px">Programme ${simulate ? 'testen' : 'auslösen'}</div>
          ${playable.length === 0
            ? `<p class="gs-empty">(keine startbaren Programme – Gerät online &amp; konfiguriert?)</p>`
            : `<div class="gs-list">${playable.map((raw) => `
                <div class="gs-row">
                  <span class="gs-ic">${bell}</span>
                  <div class="grow"><div class="name">${esc(decodeName(raw))}</div></div>
                  <button class="gs-btn ${simulate ? 'gs-sim-btn' : 'gs-ring'} fire" data-name="${esc(raw)}"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>${simulate ? 'Testen' : 'Läuten'}</button>
                </div>`).join('')}</div>
               <div class="gs-foot"><button class="gs-btn ${simulate ? 'gs-sim-btn' : 'gs-stop'}" id="stopall"><svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>${simulate ? 'Stop testen' : 'Alles stoppen'}</button></div>`}
        </section>

        <section class="gs-card">
          <div class="gs-head"><h2>Ereignis-Log</h2><span class="gs-count">◀ Antwort · ▶ gesendet · ⚙ Simulation</span><span class="gs-spacer"></span><button class="gs-btn gs-ghost" id="log-clear">Leeren</button></div>
          <div class="gs-log" id="log"></div>
        </section>

        <section class="gs-card">
          <div class="gs-head"><h2>Gerät</h2></div>
          <div class="gs-fields">
            <label>Seriennummer</label><input type="text" id="dev-serial" value="${esc(d?.serial ?? '')}" placeholder="VH-XXXXXX">
            <label>Geräte-Passwort</label><input type="password" id="dev-pw" value="${esc(d?.devicePw ?? '')}" placeholder="geheim">
            <label>Broker-URL</label><input type="text" id="dev-broker" value="${esc(d?.brokerUrl ?? 'wss://hew-voco.de:8084/mqtt')}">
          </div>
          <p class="gs-note"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>Seriennummer + Passwort erlauben das Läuten – Modulzugriff einschränken. Verbinden &amp; Status lesen ist ungefährlich.</p>
          <div class="gs-foot" style="justify-content:flex-start;margin-top:14px"><button class="gs-btn gs-primary" id="save-dev">Gerät speichern &amp; verbinden</button></div>
        </section>

        <section class="gs-card">
          <div class="gs-head"><h2>Automatik-Regeln</h2><span class="gs-spacer"></span><button class="gs-btn gs-ghost" id="add-rule"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>Regel hinzufügen</button></div>
          <p style="color:var(--gs-dim);font-size:13.5px;margin:-4px 0 12px">Vom Gateway-Dienst für automatisches Läuten genutzt (Termin → Programm).</p>
          <div id="rules"></div>
          <div class="gs-foot" style="justify-content:flex-start;margin-top:12px"><button class="gs-btn gs-primary" id="save-rules">Regeln speichern</button><span id="save-msg" style="margin-left:10px;color:var(--gs-success-strong);font-weight:600;align-self:center"></span></div>
        </section>
      </div>

      <button class="gs-fab" id="fab"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/></svg>Feedback${errorCount ? `<span class="badge">${errorCount}</span>` : ''}</button>
      <div id="modal-mount"></div>
      <div class="gs-toast" id="toast"></div>
    </div>`;

    renderRules();
    updateLogEl();
    wire();
}

function updateFab() {
    const fab = document.getElementById('fab');
    if (!fab) return;
    let badge = fab.querySelector('.badge') as HTMLElement | null;
    if (errorCount > 0) {
        if (!badge) { badge = document.createElement('span'); badge.className = 'badge'; fab.appendChild(badge); }
        badge.textContent = String(errorCount);
    } else if (badge) { badge.remove(); }
}

function updateLogEl() {
    const el = document.getElementById('log');
    if (!el) return;
    if (logLines.length === 0) { el.innerHTML = `<span style="color:#7c8b99">(noch keine Ereignisse – „Aktualisieren" drücken oder Gerät verbinden)</span>`; return; }
    const icon = (d: string) => (d === 'in' ? '◀' : d === 'sim' ? '⚙' : '▶');
    el.innerHTML = logLines.map((e) => `<div><span class="ts">${e.t}</span> <span class="${e.dir}">${icon(e.dir)}</span> ${esc(e.line)}</div>`).join('');
}

function calendarOptions(sel: number | null) {
    return [`<option value="">(jeder Kalender)</option>`]
        .concat(calendars.map((c) => `<option value="${c.id}" ${sel === c.id ? 'selected' : ''}>${esc(c.name)}</option>`)).join('');
}

function renderRules() {
    const wrap = document.getElementById('rules');
    if (!wrap) return;
    if (cfg.rules.length === 0) { wrap.innerHTML = `<p class="gs-empty">(noch keine Regeln)</p>`; return; }
    const pgsList = voco?.status.playable.map((r) => decodeName(r)) ?? [];
    wrap.innerHTML = cfg.rules.map((r, i) => `
      <div data-i="${i}" style="border:1px solid var(--gs-border);border-radius:var(--gs-radius-sm);padding:12px;margin-bottom:10px;display:grid;grid-template-columns:150px 1fr;gap:9px 12px;align-items:center">
        <label style="color:var(--gs-dim);font-size:14px">Name</label><input type="text" class="r-name" value="${esc(r.name)}">
        <label style="color:var(--gs-dim);font-size:14px">Kalender</label><select class="r-cal">${calendarOptions(r.calendarId)}</select>
        <label style="color:var(--gs-dim);font-size:14px">Veranstaltungsart</label><input type="text" class="r-cat" value="${esc(r.category ?? '')}" placeholder="(egal) z. B. Gottesdienst">
        <label style="color:var(--gs-dim);font-size:14px">Läuteprogramm</label><input type="text" class="r-pgs" value="${esc(r.pgsName)}" list="pgs-${i}" placeholder="Name des Sofort-PGS"><datalist id="pgs-${i}">${pgsList.map((n) => `<option value="${esc(n)}">`).join('')}</datalist>
        <label style="color:var(--gs-dim);font-size:14px">Vorlauf (Min.)</label><input type="number" class="r-lead" min="0" value="${r.leadMinutes}">
        <label style="color:var(--gs-dim);font-size:14px">Aktiv</label><label class="gs-switch"><input type="checkbox" class="r-active" ${r.active ? 'checked' : ''}></label>
        <div></div><button class="gs-btn gs-stop r-del" style="justify-self:start;padding:6px 12px">Löschen</button>
      </div>`).join('');
}

function collectRules(): MappingRule[] {
    const out: MappingRule[] = [];
    document.querySelectorAll('#rules [data-i]').forEach((el) => {
        const i = parseInt((el as HTMLElement).dataset.i!, 10);
        const g = (s: string) => el.querySelector(s) as HTMLInputElement;
        const cal = (el.querySelector('.r-cal') as HTMLSelectElement).value;
        out.push({
            id: cfg.rules[i]?.id ?? Math.random().toString(36).slice(2),
            name: g('.r-name').value.trim() || 'Regel',
            calendarId: cal ? parseInt(cal, 10) : null,
            category: g('.r-cat').value.trim() || null,
            pgsName: g('.r-pgs').value.trim(),
            leadMinutes: parseInt(g('.r-lead').value, 10) || 0,
            active: g('.r-active').checked,
        });
    });
    return out;
}

/* ---------------- Feedback modal ---------------- */
function openFeedback() {
    const mount = document.getElementById('modal-mount');
    if (!mount) return;
    mount.innerHTML = `
      <div class="gs-backdrop" id="fb-backdrop">
        <div class="gs-modal" role="dialog" aria-modal="true" aria-label="Feedback">
          <h3>Feedback senden</h3>
          <p class="hint">Geht direkt an die Entwicklung. Technische Angaben (Instanz, Version, letzte Ereignisse) werden zur Fehlersuche angehängt – <b>keine</b> Passwörter.</p>
          <div class="field"><label>Name (optional)</label><input type="text" id="fb-name" placeholder="Dein Name"></div>
          <div class="field"><label>E-Mail für Rückfragen (optional)</label><input type="email" id="fb-email" placeholder="du@gemeinde.de"></div>
          <div class="field"><label>Art</label><select id="fb-cat"><option>Fehler / etwas funktioniert nicht</option><option>Verbesserungsvorschlag</option><option>Frage</option><option>Sonstiges</option></select></div>
          <div class="field"><label>Nachricht</label><textarea id="fb-msg" rows="4" placeholder="Was ist passiert / was wünschst du dir?"></textarea></div>
          <div class="actions"><button class="gs-btn gs-ghost" id="fb-cancel">Abbrechen</button><button class="gs-btn gs-primary" id="fb-send">Senden</button></div>
        </div>
      </div>`;
    const close = () => (mount.innerHTML = '');
    document.getElementById('fb-cancel')!.addEventListener('click', close);
    document.getElementById('fb-backdrop')!.addEventListener('click', (e) => { if (e.target === e.currentTarget) close(); });
    document.getElementById('fb-send')!.addEventListener('click', async () => {
        const f: FeedbackFields = {
            name: (document.getElementById('fb-name') as HTMLInputElement).value.trim(),
            email: (document.getElementById('fb-email') as HTMLInputElement).value.trim(),
            category: (document.getElementById('fb-cat') as HTMLSelectElement).value,
            message: (document.getElementById('fb-msg') as HTMLTextAreaElement).value.trim(),
        };
        if (!f.message) { toast('Bitte eine Nachricht eingeben.'); return; }
        const res = await submitFeedback(f, ctx());
        close();
        if (res.sent) toast('Danke! Feedback wurde gesendet.');
        else if (res.mailto) { toast('E-Mail-Programm wird geöffnet …'); window.location.href = res.mailto; }
        else toast('Konnte nicht senden.');
    });
}

let toastTimer: number | undefined;
function toast(msg: string) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => el.classList.remove('show'), 2600);
}

function wire() {
    document.getElementById('sim-toggle')?.addEventListener('click', () => setSimulate(!simulate));
    document.getElementById('log-clear')?.addEventListener('click', () => { logLines = []; updateLogEl(); });
    document.getElementById('refresh')?.addEventListener('click', () => voco?.requestSync());
    document.getElementById('fab')?.addEventListener('click', openFeedback);
    document.getElementById('stopall')?.addEventListener('click', () => {
        if (simulate) { voco?.stopAll(); toast('Simulation: nichts gesendet.'); }
        else if (confirm('Wirklich ALLES stoppen?')) voco?.stopAll();
    });
    document.querySelectorAll('.fire').forEach((b) => b.addEventListener('click', () => fire((b as HTMLElement).dataset.name!)));
    document.getElementById('save-dev')?.addEventListener('click', async () => {
        const dev: DeviceConfig = {
            serial: (document.getElementById('dev-serial') as HTMLInputElement).value.trim(),
            devicePw: (document.getElementById('dev-pw') as HTMLInputElement).value.trim(),
            brokerUrl: (document.getElementById('dev-broker') as HTMLInputElement).value.trim() || undefined,
        };
        cfg.device = dev;
        try { await store.saveDevice(dev); } catch (e) { handleError('saveDevice', e); }
        connectVoco();
        render();
    });
    document.getElementById('add-rule')?.addEventListener('click', () => { cfg.rules = collectRules(); cfg.rules.push(newRule()); renderRules(); wire(); });
    document.querySelectorAll('.r-del').forEach((b) => b.addEventListener('click', (e) => {
        const i = parseInt(((e.target as HTMLElement).closest('[data-i]') as HTMLElement).dataset.i!, 10);
        cfg.rules = collectRules(); cfg.rules.splice(i, 1); renderRules(); wire();
    }));
    document.getElementById('save-rules')?.addEventListener('click', async () => {
        cfg.rules = collectRules();
        try {
            await store.saveRules(cfg.rules);
            const m = document.getElementById('save-msg');
            if (m) { m.textContent = '✓ gespeichert'; setTimeout(() => (m.textContent = ''), 2500); }
        } catch (e) { handleError('saveRules', e); }
    });
}

boot();
