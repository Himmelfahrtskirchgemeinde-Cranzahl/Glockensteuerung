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

/**
 * Sonderzeichen-Mapping (Steuerbyte -> Zeichen), nur für die ANZEIGE.
 *
 * Die Folge ist lückenlos: 0x24 bis 0x2B, also `$ % & ' ( ) * +`. Hier standen
 * für ö und ü einmal 0x30 und 0x31 – das sind aber die Ziffern **0 und 1**.
 * Genau daran scheiterte die Anzeige: Aus „TESTLÄUTEN - 1 min." wurde
 * „TESTLÄUTEN - ü min.". Die Verwechslung ist leicht zu erklären: Die Werte
 * stehen im Original dezimal (36…43), und wer sie als 24, 25, … 29, 30, 31
 * weiterzählt, trifft bei den letzten beiden statt 0x2A/0x2B die Ziffern.
 */
const DECODE: Record<number, string> = {
    0x24: ':', 0x25: 'ß', 0x26: 'Ä', 0x27: 'Ö',
    0x28: 'Ü', 0x29: 'ä', 0x2a: 'ö', 0x2b: 'ü',
};

/**
 * Zeichen der DOS-Zeichensätze CP437/CP850 im Bereich 0x80–0x9F.
 *
 * Genau dort schickt die Anlage ihre Umlaute: „TESTLÄUTEN" kommt als
 * `TESTL` + `0x8E` + `UTEN` an. In Latin-1 ist 0x8E ein unsichtbares
 * Steuerzeichen – die Anzeige blieb deshalb leer bzw. zeigte ein Kästchen.
 *
 * Der Bereich 0x80–0x9F ist der verlässliche Fingerzeig: In Latin-1 stehen dort
 * ausschließlich Steuerzeichen, die in einem Programmnamen nie vorkommen. Taucht
 * eines auf, ist der Text DOS-kodiert. CP437 und CP850 sind in diesem Bereich
 * identisch, ebenso beim ß (0xE1) – deshalb muss man sie hier nicht
 * auseinanderhalten.
 */
const DOS: Record<number, string> = {
    0x80: 'Ç', 0x81: 'ü', 0x82: 'é', 0x83: 'â', 0x84: 'ä', 0x85: 'à', 0x86: 'å',
    0x87: 'ç', 0x88: 'ê', 0x89: 'ë', 0x8a: 'è', 0x8b: 'ï', 0x8c: 'î', 0x8d: 'ì',
    0x8e: 'Ä', 0x8f: 'Å', 0x90: 'É', 0x91: 'æ', 0x92: 'Æ', 0x93: 'ô', 0x94: 'ö',
    0x95: 'ò', 0x96: 'û', 0x97: 'ù', 0x98: 'ÿ', 0x99: 'Ö', 0x9a: 'Ü', 0x9b: '¢',
    0x9c: '£', 0x9d: '¥', 0x9e: '₧', 0x9f: 'ƒ', 0xe1: 'ß',
};

/**
 * Macht aus einer Bytefolge Text – ohne dabei Umlaute zu verlieren.
 *
 * Die Anlage schickt ihre Namen als rohe Bytes, und welchen Zeichensatz sie
 * dabei benutzt, hängt vom Gerät ab. Geraten wird deshalb nicht, sondern der
 * Reihe nach geprüft:
 *
 * 1. **UTF-8**, wenn die Folge als solches aufgeht – anders kommt eine gültige
 *    Mehrbyte-Folge praktisch nicht zustande.
 * 2. **DOS (CP437/CP850)**, sobald ein Zeichen aus 0x80–0x9F auftaucht. So
 *    spricht die Anlage tatsächlich.
 * 3. Sonst bleibt es bei **Latin-1**, wie es hereinkam.
 *
 * Wichtig ist die Reihenfolge davor: Gelesen wird zuerst Latin-1 (ein Byte =
 * ein Zeichen), denn die Längenangaben im Listenformat zählen Bytes. Erst der
 * fertig geschnittene Name wird hier zurechtgerückt.
 */
function alsText(latin1: string): string {
    // Reines ASCII? Dann gibt es nichts zu entscheiden.
    if (!/[\u0080-\u00ff]/.test(latin1)) return latin1;
    try {
        const bytes = Uint8Array.from(latin1, (c) => c.charCodeAt(0) & 0xff);
        return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch {
        // kein UTF-8
    }
    if (/[\u0080-\u009f]/.test(latin1)) {
        return [...latin1].map((c) => DOS[c.charCodeAt(0)] ?? c).join('');
    }
    return latin1;
}

/**
 * Bleibt nach der Umwandlung etwas Unlesbares übrig, sagt das hier, welches
 * Byte es war.
 *
 * Damit endet das Rätselraten: Steht in der Anzeige ein Kästchen, nennt das
 * Ereignis-Log den Zahlenwert dahinter – und die Zeichentabelle oben lässt sich
 * gezielt ergänzen, statt die nächste Runde zu vermuten.
 */
export function unlesbareZeichen(text: string): string[] {
    const raus = new Set<string>();
    for (const c of text) {
        const code = c.charCodeAt(0);
        if ((code >= 0x80 && code <= 0x9f) || code === 0xfffd || (code < 0x20 && code !== 0x0a)) {
            raus.add('0x' + code.toString(16).toUpperCase().padStart(2, '0'));
        }
    }
    return [...raus];
}

export function decodeName(raw: string): string {
    let out = '';
    for (const ch of alsText(raw)) out += DECODE[ch.charCodeAt(0)] ?? ch;
    return out;
}

/**
 * Rohe Nutzdaten als Text, ein Byte je Zeichen (Latin-1).
 *
 * Bewusst von Hand statt über `payload.toString('latin1')`: Im Browser ist
 * `Buffer` nachgebaut, und ob der Nachbau diesen Zeichensatz beherrscht, ist
 * nicht garantiert. Fiele er auf UTF-8 zurück, wären Umlaute schon hier
 * zerstört – und die Längenangaben im Listenformat gingen mit ihnen kaputt,
 * weil UTF-8 für ein Zeichen zwei Bytes braucht. Dann stünde nicht nur ein
 * falscher Buchstabe da, sondern die halbe Liste wäre verschoben.
 */
export function binaerText(payload: Uint8Array | { length: number; [i: number]: number }): string {
    let out = '';
    for (let i = 0; i < payload.length; i++) out += String.fromCharCode(payload[i] & 0xff);
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

/** Programm-Katalog des Geräts (aus /syncdata). */
export type VocoCatalog = {
    sPGS: string[];          // Sofort-PGS
    programsteps: string[];  // Programmschritte (Vorlagen)
    melodies: string[];      // Melodien (Name enthält oft die Dauer)
};

/** Extrahiert alle "..."-Werte aus einem Abschnitt (Werte dürfen Kommas enthalten). */
function extractQuoted(seg: string): string[] {
    return (seg.match(/"([^"]*)"/g) ?? []).map((s) => s.slice(1, -1).trim()).filter(Boolean);
}

/**
 * Parst den /syncdata-Katalog. Abschnitte sind komma-getrennte KEY_…-Blöcke,
 * die Listen (sPGS, programsteps, melodies) enthalten `_`-getrennte, doppelt
 * gequotete Namen. Wir schneiden je Abschnitt zwischen seinem und dem nächsten
 * bekannten Schlüssel und ziehen die gequoteten Namen heraus.
 */
export function parseCatalog(payload: string): VocoCatalog {
    const section = (key: string, next: string): string => {
        const s = payload.indexOf(`,${key}_`);
        if (s < 0) return '';
        const from = s + key.length + 2;
        let e = payload.indexOf(`,${next}`, from);
        if (e < 0) e = payload.length;
        return payload.slice(from, e);
    };
    return {
        sPGS: extractQuoted(section('sPGS', 'programsteps')),
        programsteps: extractQuoted(section('programsteps', 'pgsmodes')),
        melodies: extractQuoted(section('melodies', 'clockbhvs')),
    };
}

export class VocoMqtt {
    private client?: MqttClient;
    private base: string;
    private cfg: Required<VocoConfig>;
    public status: VocoStatus = { online: null, playable: [], stoppable: [] };
    public catalog: VocoCatalog = { sPGS: [], programsteps: [], melodies: [] };
    public onUpdate?: () => void;
    /** Simulationsmodus: sendet KEINE auslösenden Befehle, protokolliert sie nur. */
    public simulate = true;
    public onLog?: (line: string, dir: 'in' | 'out' | 'sim' | 'info') => void;
    private syncdataLogged = false;

    private log(line: string, dir: 'in' | 'out' | 'sim' | 'info') { this.onLog?.(line, dir); }

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
                this.log(reconnected ? 'wieder mit Broker verbunden' : 'mit Broker verbunden', 'info');
                resolve();
            });
            // Nur der ERSTE Verbindungsfehler ist fatal. Spaetere sind vom
            // Auto-Reconnect abgedeckt und werden nur als Info geloggt (kein
            // gemeldeter Fehler).
            c.on('error', (e) => {
                if (!settled) { settled = true; reject(e); }
                else this.log('Verbindung unterbrochen – verbinde neu …', 'info');
            });
            c.on('offline', () => { if (settled) this.log('Verbindung unterbrochen – verbinde neu …', 'info'); });
            c.on('message', (topic, payload) => this.onMessage(topic, binaerText(payload)));
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
        this.pub('/fetchdata', '1'); // Katalog (sPGS, Programmschritte, Melodien …) anfordern
        this.log('Status/Programme angefragt (lesend)', 'info');
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
        // Hinweis zur Kennzeichnung: Gerätestatus, Listen, Katalog und Echos sind
        // laufende INFOS (ℹ). Als „Antwort" (◀) gilt nur echtes Läuten – das wird
        // in App.vue aus der Änderung der laufenden Programme abgeleitet.
        // Fuer die Anzeige im Ereignis-Log zurechtgerueckt - sonst stuenden dort
        // die rohen Bytes. Das Parsen weiter unten arbeitet weiter mit `payload`,
        // weil die Laengenangaben Bytes zaehlen.
        const lesbar = decodeName(payload);
        const short = lesbar.length > 80 ? lesbar.slice(0, 80) + '…' : lesbar;
        if (sub === '/connection') {
            this.status.online = payload === '1';
            this.log(`Gerät meldet: ${payload === '1' ? 'online' : 'offline'}`, 'info');
        } else if (sub === '/sendpgsD') {
            const i = payload.indexOf(':');
            if (i >= 0) {
                this.status.playable = parseLenPrefixed(payload.substring(0, i));
                this.status.stoppable = parseLenPrefixed(payload.substring(i + 1));
            }
            this.log(`Programmliste empfangen (${this.status.playable.length} startbar, ${this.status.stoppable.length} laufend)`, 'info');
            // Falls ein Zeichen uebrig bleibt, das sich nicht zuordnen laesst:
            // hier steht, welches es war - sonst sieht man nur ein Kaestchen.
            const offen = [...new Set(this.status.playable.flatMap((r) => unlesbareZeichen(decodeName(r))))];
            if (offen.length) {
                this.log(`Hinweis: In den Programmnamen steht ein Zeichen, das sich nicht `
                    + `zuordnen laesst (${offen.join(', ')}). Bitte melden - dann kann es `
                    + `ergaenzt werden.`, 'info');
            }
        } else if (sub === '/sw') {
            this.log(`Schlagwerk: ${payload}`, 'info');
        } else if (sub === '/auto') {
            this.log(`Automatik: ${payload}`, 'info');
        } else if (sub === '/syncinfo') {
            this.log(`Statusinfo empfangen: ${short}`, 'info');
        } else if (sub === '/syncdata') {
            // Katalog parsen: Sofort-PGS, Programmschritte, Melodien.
            this.catalog = parseCatalog(payload);
            const c = this.catalog;
            if (!this.syncdataLogged) {
                this.syncdataLogged = true;
                this.log(`Katalog empfangen: ${c.sPGS.length} Sofort-PGS, ${c.melodies.length} Melodien, ${c.programsteps.length} Programmschritte`, 'info');
            } else {
                this.log('Katalog aktualisiert', 'info');
            }
        } else if (sub === '/fetchinfo' || sub === '/fetchdata' || sub === '/playpgsD') {
            // Echo der eigenen (retained) Anfragen – als Info protokollieren.
            this.log(`Echo ${sub}: ${short}`, 'info');
        } else {
            this.log(`${sub}: ${short}`, 'info');
        }
        this.onUpdate?.();
    }
}
