import { churchtoolsClient } from '@churchtools/churchtools-client';
import { ConfigStore, newRule, type AppConfig, type DeviceConfig, type MappingRule } from './config';
import { VocoMqtt, decodeName } from './voco/mqtt';

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

function esc(s: string) {
    return (s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));
}

async function boot() {
    app.innerHTML = `<p style="padding:1rem">Lade …</p>`;
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
        app.innerHTML = `<div style="padding:1rem;color:#b00">Fehler beim Start: ${esc(String(e))}</div>`;
    }
}

function connectVoco() {
    if (!cfg.device) return;
    voco?.disconnect();
    voco = new VocoMqtt(cfg.device);
    voco.onUpdate = render;
    voco.connect().catch((e) => console.error('MQTT', e));
}

function render() {
    const d = cfg.device;
    const online = voco?.status.online;
    const onlineTxt = online === null || online === undefined ? '– (verbinde …)' : online ? 'online ✅' : 'offline ⚠️';
    const playable = voco?.status.playable ?? [];

    app.innerHTML = `
    <div style="max-width:820px;margin:0 auto;padding:1rem;font-family:system-ui,sans-serif">
      <h1 style="margin:0 0 .25rem">🔔 Glockensteuerung</h1>
      <p style="color:#666;margin:.2rem 0 1rem">ChurchTools ⇄ VOCO-futura ST5</p>

      <section style="border:1px solid #ddd;border-radius:8px;padding:1rem;margin-bottom:1rem">
        <h2 style="margin:.2rem 0">Status</h2>
        <p>Gerät: <b>${d?.serial ? esc(d.serial) : '(nicht konfiguriert)'}</b> — ${onlineTxt}
           <button id="refresh" style="margin-left:.5rem">Aktualisieren</button></p>
        <h3 style="margin:.6rem 0 .3rem">Programme sofort auslösen</h3>
        ${playable.length === 0
            ? `<p style="color:#888;font-style:italic">(keine startbaren Programme – Gerät online &amp; konfiguriert?)</p>`
            : `<ul style="list-style:none;padding:0;margin:0">${playable.map((raw) => `
                <li style="display:flex;align-items:center;gap:.5rem;padding:.2rem 0">
                  <button class="fire" data-name="${esc(raw)}" style="background:#21ba45;color:#fff;border:0;border-radius:4px;padding:.35rem .7rem;cursor:pointer">▶ Läuten</button>
                  <span>${esc(decodeName(raw))}</span>
                </li>`).join('')}</ul>
               <button id="stopall" style="margin-top:.5rem;background:#db2828;color:#fff;border:0;border-radius:4px;padding:.35rem .7rem;cursor:pointer">■ Alles stoppen</button>`}
      </section>

      <section style="border:1px solid #ddd;border-radius:8px;padding:1rem;margin-bottom:1rem">
        <h2 style="margin:.2rem 0">Gerät</h2>
        <div style="display:grid;grid-template-columns:160px 1fr;gap:.4rem;align-items:center;max-width:560px">
          <label>Seriennummer</label><input id="dev-serial" value="${esc(d?.serial ?? '')}" placeholder="VH-XXXXXX">
          <label>Geräte-Passwort</label><input id="dev-pw" type="password" value="${esc(d?.devicePw ?? '')}" placeholder="geheim">
          <label>Broker-URL</label><input id="dev-broker" value="${esc(d?.brokerUrl ?? 'wss://hew-voco.de:8084/mqtt')}">
        </div>
        <p style="color:#a60;font-size:.85rem;margin:.5rem 0 0">🔐 Seriennummer + Passwort erlauben das Läuten. Zugriff auf dieses Modul entsprechend einschränken.</p>
        <button id="save-dev" style="margin-top:.6rem">Gerät speichern &amp; verbinden</button>
      </section>

      <section style="border:1px solid #ddd;border-radius:8px;padding:1rem">
        <h2 style="margin:.2rem 0">Automatik-Regeln (Termin → Programm)</h2>
        <p style="color:#666;font-size:.9rem;margin:.2rem 0 .6rem">Diese Regeln nutzt der Gateway-Dienst, um automatisch zur Termin-Zeit zu läuten.</p>
        <div id="rules"></div>
        <button id="add-rule" style="margin-top:.6rem">+ Regel hinzufügen</button>
        <button id="save-rules" style="margin-top:.6rem;margin-left:.5rem">Regeln speichern</button>
        <span id="save-msg" style="margin-left:.5rem;color:#21924a"></span>
      </section>
    </div>`;

    renderRules();
    wire();
}

function calendarOptions(sel: number | null): string {
    const opts = [`<option value="">(jeder Kalender)</option>`]
        .concat(calendars.map((c) => `<option value="${c.id}" ${sel === c.id ? 'selected' : ''}>${esc(c.name)}</option>`));
    return opts.join('');
}

function renderRules() {
    const wrap = document.getElementById('rules');
    if (!wrap) return;
    if (cfg.rules.length === 0) {
        wrap.innerHTML = `<p style="color:#888;font-style:italic">(noch keine Regeln)</p>`;
        return;
    }
    const pgsList = voco?.status.playable.map((r) => decodeName(r)) ?? [];
    wrap.innerHTML = cfg.rules.map((r, i) => `
      <div data-i="${i}" style="border:1px solid #eee;border-radius:6px;padding:.6rem;margin-bottom:.5rem;display:grid;grid-template-columns:150px 1fr;gap:.35rem;align-items:center">
        <label>Name</label><input class="r-name" value="${esc(r.name)}">
        <label>Kalender</label><select class="r-cal">${calendarOptions(r.calendarId)}</select>
        <label>Veranstaltungsart</label><input class="r-cat" value="${esc(r.category ?? '')}" placeholder="(egal) z. B. Gottesdienst">
        <label>Läuteprogramm (PGS)</label>
        <input class="r-pgs" value="${esc(r.pgsName)}" list="pgs-list-${i}" placeholder="Name des Sofort-PGS">
        <datalist id="pgs-list-${i}">${pgsList.map((n) => `<option value="${esc(n)}">`).join('')}</datalist>
        <label>Vorlauf (Min.)</label><input class="r-lead" type="number" min="0" value="${r.leadMinutes}">
        <label>Aktiv</label><input class="r-active" type="checkbox" ${r.active ? 'checked' : ''}>
        <div></div><button class="r-del" style="justify-self:start;color:#db2828">Regel löschen</button>
      </div>`).join('');
}

function collectRules(): MappingRule[] {
    const out: MappingRule[] = [];
    document.querySelectorAll('#rules [data-i]').forEach((el) => {
        const i = parseInt((el as HTMLElement).dataset.i!, 10);
        const g = (sel: string) => (el.querySelector(sel) as HTMLInputElement);
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

function wire() {
    document.getElementById('refresh')?.addEventListener('click', () => voco?.requestSync());
    document.getElementById('stopall')?.addEventListener('click', () => voco?.stopAll());
    document.querySelectorAll('.fire').forEach((b) =>
        b.addEventListener('click', () => {
            const name = (b as HTMLElement).dataset.name!;
            if (confirm(`Programm wirklich AUSLÖSEN?\n\n${decodeName(name)}\n\nDas löst echtes Läuten aus.`)) voco?.start(name);
        }),
    );
    document.getElementById('save-dev')?.addEventListener('click', async () => {
        const dev: DeviceConfig = {
            serial: (document.getElementById('dev-serial') as HTMLInputElement).value.trim(),
            devicePw: (document.getElementById('dev-pw') as HTMLInputElement).value.trim(),
            brokerUrl: (document.getElementById('dev-broker') as HTMLInputElement).value.trim() || undefined,
        };
        cfg.device = dev;
        await store.saveDevice(dev);
        connectVoco();
        render();
    });
    document.getElementById('add-rule')?.addEventListener('click', () => {
        cfg.rules = collectRules();
        cfg.rules.push(newRule());
        renderRules();
        wire();
    });
    document.querySelectorAll('.r-del').forEach((b) =>
        b.addEventListener('click', (e) => {
            const i = parseInt(((e.target as HTMLElement).closest('[data-i]') as HTMLElement).dataset.i!, 10);
            cfg.rules = collectRules();
            cfg.rules.splice(i, 1);
            renderRules();
            wire();
        }),
    );
    document.getElementById('save-rules')?.addEventListener('click', async () => {
        cfg.rules = collectRules();
        await store.saveRules(cfg.rules);
        const m = document.getElementById('save-msg');
        if (m) { m.textContent = '✓ gespeichert'; setTimeout(() => (m.textContent = ''), 2500); }
    });
}

boot();
