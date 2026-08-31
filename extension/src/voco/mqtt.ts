/**
 * VOCO-futura Steuerung per MQTT (WebSocket) – Browser-Client.
 * Spiegelt das Protokoll der HEW-Web-App (app.hew-voco.de), siehe
 * docs/VOCO-MQTT-Protokoll.md.
 *
 * Nutzt MQTT.js (Paket "mqtt"), das im Browser MQTT-over-WSS spricht.
 */
import mqtt, { type MqttClient } from 'mqtt';

export interface VocoConfig {
    serial: string;        // z.B. VH-XXXXXX
    devicePw: string;      // Geraete-Passwort (Geheimnis!)
    brokerUrl?: string;    // Standard: wss://hew-voco.de:8084/mqtt
    brokerUser?: string;   // Standard: hewWeb
    brokerPass?: string;   // Standard: vocoWeb
}

// Sonderzeichen-Mapping (Steuerbyte -> Zeichen) nur fuer ANZEIGE
const DECODE: Record<number, string> = {
    0x24: ':', 0x25: 'ß', 0x26: 'Ä', 0x27: 'Ö',
    0x28: 'Ü', 0x29: 'ä', 0x30: 'ö', 0x31: 'ü',
};

export function decodeName(raw: string): string {
    let out = '';
    for (const ch of raw) out += DECODE[ch.charCodeAt(0)] ?? ch;
    return out;
}

/** Parst das laengenpraefix-Format LL_<name>X aus /sendpgsD. */
function parseLenPrefixed(s: string): string[] {
    const out: string[] = [];
    let idx = 0;
    const prefixes = ['Sofort PGS: ', 'Uhrschlag: ', 'Melodie: ', 'PGS: '];
    while (idx < s.length) {
        for (const p of prefixes) {
            if (s.substr(idx, p.length) === p) { idx += p.length; break; }
        }
        if (idx + 3 > s.length) break;
        const lnStr = s.substr(idx, 2);
        if (!/^\d\d$/.test(lnStr)) break;
        const ln = parseInt(lnStr, 10);
        out.push(s.substr(idx + 3, ln));
        idx += ln + 4;
    }
    return out;
}

export type VocoStatus = {
    online: boolean | null;
    playable: string[];   // rohe Namen der startbaren PGS
    stoppable: string[];
};

export class VocoMqtt {
    private client?: MqttClient;
    private base: string;
    private cfg: Required<VocoConfig>;
    public status: VocoStatus = { online: null, playable: [], stoppable: [] };
    public onUpdate?: () => void;
    /** Simulationsmodus: sendet KEINE auslösenden Befehle, protokolliert sie nur. */
    public simulate = true;
    public onLog?: (line: string, dir: 'in' | 'out' | 'sim') => void;

    private log(line: string, dir: 'in' | 'out' | 'sim') { this.onLog?.(line, dir); }

    constructor(cfg: VocoConfig) {
        this.cfg = {
            brokerUrl: 'wss://hew-voco.de:8084/mqtt',
            brokerUser: 'hewWeb',
            brokerPass: 'vocoWeb',
            ...cfg,
        };
        this.base = `hew/voco/${this.cfg.serial}${this.cfg.devicePw}`;
    }

    connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            const c = mqtt.connect(this.cfg.brokerUrl, {
                username: this.cfg.brokerUser,
                password: this.cfg.brokerPass,
                clientId: `${this.cfg.serial}-web-ct-${Math.floor(performance.now())}`,
                clean: true,
                keepalive: 600,
                reconnectPeriod: 5000,
                protocolVersion: 4,
            });
            this.client = c;
            let settled = false;
            c.on('connect', () => {
                const reconnected = settled;
                settled = true;
                c.subscribe(`${this.base}/#`);
                this.requestSync();
                if (reconnected) this.log('wieder verbunden', 'in');
                resolve();
            });
            // Nur der ERSTE Verbindungsfehler ist fatal. Spaetere sind vom
            // Auto-Reconnect abgedeckt und werden nur als Info geloggt (kein
            // gemeldeter Fehler).
            c.on('error', (e) => {
                if (!settled) { settled = true; reject(e); }
                else this.log('Verbindung unterbrochen – verbinde neu …', 'in');
            });
            c.on('offline', () => { if (settled) this.log('Verbindung unterbrochen – verbinde neu …', 'in'); });
            c.on('message', (topic, payload) => this.onMessage(topic, payload.toString('latin1')));
        });
    }

    disconnect() { this.client?.end(true); }

    private pub(subtopic: string, payload: string) {
        this.client?.publish(this.base + subtopic, payload, { qos: 0, retain: false });
    }

    /**
     * Auslösende Befehle laufen hierüber. Im Simulationsmodus wird NICHTS
     * gesendet – der Befehl wird nur protokolliert.
     */
    private command(subtopic: string, payload: string, human: string) {
        if (this.simulate) {
            this.log(`SIMULATION – würde senden: ${payload}  (${human})`, 'sim');
            return;
        }
        this.pub(subtopic, payload);
        this.log(`gesendet: ${payload}  (${human})`, 'out');
    }

    /** Statusinfo + startbare Liste anfordern (rein lesend, immer erlaubt). */
    requestSync() {
        this.pub('/fetchinfo', 'EN');
        this.pub('/playpgsD', 'list');
        this.log('Status/Programme angefragt (lesend)', 'out');
    }

    /** Programm sofort starten. name = ROHER Name (wie empfangen). */
    start(nameRaw: string, when: string = 'INSTANT') {
        this.command('/playpgsD', `START:${nameRaw}:${when}`, `Programm „${decodeName(nameRaw)}“ auslösen`);
    }
    stop(nameRaw: string) { this.command('/playpgsD', `STOP:${nameRaw}`, `„${decodeName(nameRaw)}“ stoppen`); }
    stopAll() { this.command('/playpgsD', 'STOP:ALL', 'alles stoppen'); }

    /** Findet rohen Namen anhand des Anzeigenamens. */
    resolve(displayName: string): string | undefined {
        return this.status.playable.find(
            (raw) => decodeName(raw) === displayName || raw === displayName,
        );
    }

    private onMessage(topic: string, payload: string) {
        const sub = topic.substring(this.base.length);
        if (sub === '/connection') {
            this.status.online = payload === '1';
            this.log(`Gerät meldet: ${payload === '1' ? 'online' : 'offline'}`, 'in');
        } else if (sub === '/sendpgsD') {
            const i = payload.indexOf(':');
            if (i >= 0) {
                this.status.playable = parseLenPrefixed(payload.substring(0, i));
                this.status.stoppable = parseLenPrefixed(payload.substring(i + 1));
            }
            this.log(`Programmliste empfangen (${this.status.playable.length} startbar)`, 'in');
        } else if (sub === '/sw') {
            this.log(`Schlagwerk: ${payload}`, 'in');
        } else if (sub === '/auto') {
            this.log(`Automatik: ${payload}`, 'in');
        } else if (sub === '/syncinfo') {
            this.log('Statusinfo empfangen', 'in');
        } else if (sub === '/syncdata' || sub === '/fetchinfo' || sub === '/fetchdata' || sub === '/playpgsD') {
            // Datenlisten bzw. Echo der eigenen Anfragen (retained) – nicht loggen.
        } else {
            const short = payload.length > 80 ? payload.slice(0, 80) + '…' : payload;
            this.log(`${sub}: ${short}`, 'in');
        }
        this.onUpdate?.();
    }
}
