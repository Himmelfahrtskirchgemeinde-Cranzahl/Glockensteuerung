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
            c.on('connect', () => {
                c.subscribe(`${this.base}/#`);
                this.requestSync();
                resolve();
            });
            c.on('error', (e) => reject(e));
            c.on('message', (topic, payload) => this.onMessage(topic, payload.toString('latin1')));
        });
    }

    disconnect() { this.client?.end(true); }

    private pub(subtopic: string, payload: string) {
        this.client?.publish(this.base + subtopic, payload, { qos: 0, retain: false });
    }

    /** Statusinfo + startbare Liste anfordern. */
    requestSync() {
        this.pub('/fetchinfo', 'EN');
        this.pub('/playpgsD', 'list');
    }

    /** Programm sofort starten. name = ROHER Name (wie empfangen). */
    start(nameRaw: string, when: string = 'INSTANT') {
        this.pub('/playpgsD', `START:${nameRaw}:${when}`);
    }
    stop(nameRaw: string) { this.pub('/playpgsD', `STOP:${nameRaw}`); }
    stopAll() { this.pub('/playpgsD', 'STOP:ALL'); }

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
        } else if (sub === '/sendpgsD') {
            const i = payload.indexOf(':');
            if (i >= 0) {
                this.status.playable = parseLenPrefixed(payload.substring(0, i));
                this.status.stoppable = parseLenPrefixed(payload.substring(i + 1));
            }
        }
        this.onUpdate?.();
    }
}
