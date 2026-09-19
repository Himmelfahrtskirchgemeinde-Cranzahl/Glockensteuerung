/**
 * Konfiguration der Glockensteuerungs-Extension.
 * Persistiert im ChurchTools Key-Value-Store (customdatacategories/-values),
 * damit auch der Gateway-Dienst dieselbe Konfiguration lesen kann.
 *
 * Jedes Untermenü ist eine eigene Kategorie – so lassen sich die Rechte pro
 * Untermenü in der ChurchTools-Rechteverwaltung vergeben (Kategorie-Rechte sind
 * pro Kategorie-ID). „Steuerung" und „Ereignis-Log" halten keine Daten, dienen
 * aber als Rechte-Anker (sehen = Untermenü sichtbar, läuten erlaubt).
 */
import {
    getOrCreateModule,
    getCustomDataCategory,
    createCustomDataCategory,
    getCustomDataValues,
    createCustomDataValue,
    updateCustomDataValue,
    deleteCustomDataValue,
} from './utils/kv-store';
import type { UpdateCheck } from './update';
import {
    zusammenfuehren, nachWochen, istLogSchluessel, wocheVon,
    wochenNachAlter, aufteilen, LOG_ALT,
} from './logbuch';

export const EXT_KEY: string = import.meta.env.VITE_KEY;

/** Untermenü = Kategorie. shorty ist stabil (erscheint in der Rechteverwaltung). */
export const CATS = [
    { key: 'steuerung', shorty: 'steuerung', name: 'Steuerung', desc: 'Live-Steuerung / Läuten' },
    { key: 'log', shorty: 'ereignislog', name: 'Ereignis-Log', desc: 'Ereignis-Log' },
    { key: 'regeln', shorty: 'regeln', name: 'Automatik-Regeln', desc: 'Termin → Programm' },
    // Eigene Kategorie fuer den E-Mail-Versand. Sie enthaelt das
    // Postausgangs-Passwort und darf deshalb NICHT wie „steuerung" fuer alle
    // lesbar sein - Rechte hierauf nur an Verwalter vergeben.
    { key: 'email', shorty: 'email', name: 'E-Mail-Versand', desc: 'Postausgang (Zugangsdaten)' },
] as const;
export type CatKey = (typeof CATS)[number]['key'];

export interface DeviceConfig {
    serial: string;
    devicePw: string;       // GEHEIM – nur in ChurchTools (zugriffsbeschraenkt)
    brokerUrl?: string;     // Standard: wss://hew-voco.de:8084/mqtt
}

export interface MappingRule {
    id: string;             // lokale UUID
    name: string;           // sprechender Name der Regel
    calendarId: number | null;   // optional: nur dieser Kalender
    /**
     * Optional: nur Termine mit GENAU diesem Titel. Verglichen wird der Titel
     * des Kalender-Termins, nicht mehr die Veranstaltungsart: Eine Art laesst
     * sich einem Termin gar nicht direkt zuweisen – sie haengt an einer
     * verknuepften Veranstaltung, die es in der Praxis meist nicht gibt.
     * Der Titel steht dagegen immer am Termin.
     */
    title: string | null;
    /** Altfeld (Veranstaltungsart). Wird beim Laden nach `title` uebernommen. */
    category?: string | null;
    pgsName: string;        // Anzeigename des Sofort-PGS, der ausgeloest wird
    leadMinutes: number;    // Vorlauf: X Minuten vor Terminbeginn ausloesen
    active: boolean;
}

/**
 * Zugang zum Postausgang. Der Gateway verschickt damit; die Extension kann es
 * nicht selbst, weil ein Browser kein SMTP sprechen kann.
 *
 * Liegt in der Kategorie „email", nicht in „steuerung": Dort steht ein Passwort,
 * und „steuerung" ist bewusst fuer jeden lesbar, der das Modul bedient.
 */
export interface EmailConfig {
    host: string;
    port: number;
    user: string;
    /** GEHEIM. Verlaesst den Server nie – nur der Gateway liest ihn. */
    password: string;
    /** Absender. Leer = derselbe wie `user`. */
    from: string;
    /** Empfaenger fuer Feedback und Stoerungsmeldungen. */
    to: string;
    /** Verschluesselung: STARTTLS (ueblich, Port 587) oder SSL (Port 465). */
    security: 'starttls' | 'ssl';
    /** Feedback-Formular per E-Mail verschicken statt das Mailprogramm zu oeffnen. */
    sendFeedback: boolean;
    /** Stoerungen und Fehler melden. */
    sendErrors: boolean;
}

export function newEmailConfig(): EmailConfig {
    return {
        host: '', port: 587, user: '', password: '', from: '', to: '',
        security: 'starttls', sendFeedback: true, sendErrors: true,
    };
}

/**
 * Eine Nachricht im Postausgang. Die Extension legt sie ab, der Gateway holt
 * sie beim naechsten Durchlauf und verschickt sie.
 *
 * Liegt in „steuerung", damit JEDER etwas einstellen kann, der das Modul
 * bedient - das Feedback-Formular steht schliesslich allen offen. Hier steht
 * kein Geheimnis drin, nur Betreff und Text.
 */
export interface MailJob {
    id: string;
    subject: string;
    body: string;
    /** Wann eingestellt (ISO). Der Gateway raeumt Altes weg. */
    at: string;
    /**
     * Eilt: Der Gateway setzt dann die Kopfzeilen für hohe Priorität und
     * umgeht seine Spam-Sperre. Gedacht für das eine, was keinen Aufschub
     * duldet — dass die Automatik steht.
     */
    dringend?: boolean;
}

/** Lebenszeichen des Gateway-Dienstes (vom Gateway geschrieben, hier nur gelesen). */
export interface GatewayStatus {
    at: string;              // ISO-Zeitstempel des letzten Lebenszeichens
    rules?: number;          // wie viele Regeln der Dienst geladen hat
    simulation?: boolean;    // laeuft der Dienst im Simulationsmodus?
    device?: string | null;  // Seriennummer, die er nutzt
    /**
     * Kann Feedback per E-Mail rausgehen? Der Gateway beantwortet das, weil die
     * Extension es nicht kann: Die Zugangsdaten liegen in der Kategorie „email",
     * die normale Benutzer nicht lesen dürfen.
     */
    mail?: boolean;
    /**
     * Dürfen Störungsmeldungen raus? Ein eigener Schalter, nicht derselbe.
     *
     * Vorher hing beides an `mail` – also am Feedback-Formular. Wer „Feedback
     * per E-Mail" abschaltete, aber „Störungen melden" anließ, bekam keine
     * Störungsmeldungen, obwohl er sie eingeschaltet hatte. Fehlt das Feld
     * (älterer Gateway), gilt wie bisher `mail`.
     */
    mailFehler?: boolean;
    /**
     * Bis wann ein Neustart erwartet ist (ISO).
     *
     * Der Dienst setzt das, bevor er sich für eine Aktualisierung beendet.
     * Solange die Frist läuft, ist sein Schweigen kein Ausfall, sondern der
     * angekündigte Neustart — und darf keine Störungsmeldung auslösen.
     */
    updateBis?: string;
    /**
     * Bis wann der Dienst gerade neu aufbaut (ISO).
     *
     * Er setzt das, wenn ihm etwas dazwischengekommen ist – die Verbindung zur
     * Anlage, zu ChurchTools oder zum Netz – und er gleich einen neuen Anlauf
     * nimmt. Der Wiederanlauf dauert 15 Sekunden bis 5 Minuten; gemeldet wird
     * ein Ausfall aber schon nach zwei. Ohne diese Angabe stünde also bei jedem
     * Aussetzer „Automatik steht" samt E-Mail, obwohl der Dienst läuft und sich
     * gerade selbst hilft.
     */
    pauseBis?: string;
    /** Warum er neu aufbaut – für die Anzeige, ungekürzt im Log. */
    grund?: string;
}

/**
 * Ein vom Gateway festgehaltenes Ereignis (verbunden, getrennt, gestartet …).
 *
 * Das Ereignis-Log der Extension lebt sonst nur im Browser: Es zeigt, was seit
 * dem Öffnen der Seite geschah. Ob der Dienst nachts um drei die Verbindung
 * verloren hat, sah dort niemand. Der Dienst schreibt solche Wechsel deshalb
 * selbst mit — hier werden sie nur gelesen.
 */
export interface GatewayEvent {
    at: string;                      // ISO-Zeitstempel
    art: 'an' | 'aus' | 'info';      // verbunden / getrennt / sonstiges
    text: string;
}

/**
 * Eine Zeile des dauerhaften Ereignis-Logs.
 *
 * „Dauerhaft" heißt: in ChurchTools, nicht im Browser. Das Log lebte bisher nur
 * im Speicher der geöffneten Seite – ein Neuladen, und alles war weg. Damit war
 * nicht mehr nachzuvollziehen, wer wann geläutet hat oder wann ein Fehler
 * auftrat; genau dafür ist ein Log aber da.
 */
export interface LogEntry {
    at: string;                  // ISO-Zeitstempel
    art: string;                 // 'in' | 'out' | 'sim' | 'info' | 'gw'
    text: string;
    /** Wer es ausgelöst hat – nur bei Bedienung durch einen Menschen. */
    wer?: string;
}

/**
 * So viele Zeilen werden aufgehoben.
 *
 * Der Eintrag wird bei jedem Seitenaufruf mitgeladen, deshalb kein
 * unbegrenztes Wachstum: 300 Zeilen decken mehrere Wochen Betrieb ab und
 * bleiben klein genug, um nicht zu stören.
 */
export const LOG_MAX = 300;

/**
 * So viele Zeichen darf EIN Eintrag im Speicher haben.
 *
 * ChurchTools lässt höchstens 10 000 zu und lehnt alles darüber mit „400 –
 * Eingabe muss ein Text sein, der zwischen 0 und 10000 Zeichen enthält" ab.
 * Der Abstand nach unten ist Absicht: Gezählt wird serverseitig, und ein
 * Umlaut mehr oder weniger darf nicht über Speichern oder Verlieren
 * entscheiden.
 */
export const LOG_WERT_MAX = 9000;

/**
 * So viele Kalenderwochen werden aufgehoben.
 *
 * Danach fällt eine Woche als Ganzes weg. Zwei Monate decken jede Rückfrage
 * ab, die in der Praxis kommt („war am Sonntag vor drei Wochen etwas?"), und
 * halten den Speicher klein.
 */
export const LOG_WOCHEN = 8;

/**
 * So viele Einträge darf EINE Woche belegen.
 *
 * Eine lebhafte Woche bekommt damit Platz für rund 300 Zeilen. Die Grenze
 * schützt vor dem anderen Fall: Ein Fehler, der sich im Minutentakt
 * wiederholt, soll nicht den Speicher der Gemeinde füllen.
 */
export const LOG_TEILE = 4;

export interface AppConfig {
    device: DeviceConfig | null;
    rules: MappingRule[];
    /** Persistierter Simulations-Status der Extension (nicht Gateway). Standard: an. */
    simulate: boolean;
    /** Dauer je Programm (Anzeigename -> Minuten) für den „läuft"-Countdown. */
    durations: Record<string, number>;
    /** Letztes Lebenszeichen des Gateways – null, wenn nie eines geschrieben wurde. */
    gateway: GatewayStatus | null;
}

interface StoredValue { id: number; key: string; data: unknown }

export class ConfigStore {
    moduleId!: number;
    /** Kategorie-IDs je Untermenü (fehlt, falls nicht vorhanden & kein Anlege-Recht). */
    catIds: Partial<Record<CatKey, number>> = {};
    private valueIds: Record<string, number> = {}; // `${catKey}:${valueKey}` -> id
    private control: { simulate: boolean; durations: Record<string, number> } = { simulate: true, durations: {} };

    /**
     * Legt Modul und die vier Kategorien bei Bedarf an (erste Nutzung durch eine
     * berechtigte Person) und lädt sie sonst. Ohne diese Einträge – die beim
     * ZIP-Upload NICHT automatisch entstehen – käme „Module … not found".
     * Fehlt das Anlege-Recht (Nicht-Admin), werden nur vorhandene Kategorien
     * übernommen.
     */
    async init(): Promise<void> {
        const mod = await getOrCreateModule(
            EXT_KEY,
            'Glockensteuerung',
            'ChurchTools ⇄ VOCO-futura',
        );
        this.moduleId = mod.id;

        for (const c of CATS) {
            let cat = await getCustomDataCategory<object>(c.shorty);
            if (!cat) {
                try {
                    await createCustomDataCategory(
                        { customModuleId: this.moduleId, name: c.name, shorty: c.shorty, description: c.desc } as any,
                        this.moduleId,
                    );
                    cat = await getCustomDataCategory<object>(c.shorty);
                } catch {
                    // Kein Recht zum Anlegen – Kategorie bleibt eben unangelegt.
                }
            }
            if (cat) this.catIds[c.key] = (cat as any).id;
        }
    }

    async load(): Promise<AppConfig> {
        const cfg: AppConfig = { device: null, rules: [], simulate: true, durations: {}, gateway: null };
        // Gerät liegt in der operativen Kategorie „steuerung", damit JEDER, der das
        // Modul bedienen darf, die Verbindungsdaten lesen kann (Status/Läuten).
        // Es gehört NICHT in eine separat berechtigte „Gerät"-Kategorie – sonst sieht
        // ein reiner Betrachter das Gerät als nicht eingerichtet.
        await this.loadFrom('steuerung', 'device', (d) => { cfg.device = d as DeviceConfig; });
        await this.loadFrom('regeln', 'rules', (d) => { cfg.rules = migrateRules(d as MappingRule[]); });
        await this.loadFrom('steuerung', 'control', (d) => {
            const c = (d ?? {}) as Partial<{ simulate: boolean; durations: Record<string, number> }>;
            this.control = { simulate: c.simulate ?? true, durations: c.durations ?? {} };
        });
        cfg.simulate = this.control.simulate;
        cfg.durations = this.control.durations;
        // Lebenszeichen des Gateways – gleiche Kategorie wie das Gerät, damit es
        // jeder sieht, der das Modul bedienen darf (nicht nur Berechtigte).
        await this.loadFrom('steuerung', 'gatewayStatus', (d) => {
            cfg.gateway = (d ?? null) as GatewayStatus | null;
        });
        // Migration: früher lag das Gerät in einer eigenen „geraet"-Kategorie.
        if (!cfg.device) await this.migrateLegacyDevice((d) => { cfg.device = d; });
        return cfg;
    }

    /** Liest Gerätedaten aus der alten „geraet"-Kategorie (falls vorhanden). */
    private async migrateLegacyDevice(set: (d: DeviceConfig) => void): Promise<void> {
        try {
            const legacy = await getCustomDataCategory<object>('geraet');
            if (!legacy) return;
            const vals = await getCustomDataValues<StoredValue>((legacy as any).id, this.moduleId);
            const dev = (vals as unknown as StoredValue[]).find((v) => v.key === 'device');
            if (dev) set(dev.data as DeviceConfig);
        } catch {
            // keine Altdaten oder kein Leserecht -> ignorieren
        }
    }

    private async loadFrom(catKey: CatKey, valueKey: string, set: (data: unknown) => void): Promise<void> {
        const catId = this.catIds[catKey];
        if (!catId) return;
        try {
            const values = await getCustomDataValues<StoredValue>(catId, this.moduleId);
            for (const v of values as unknown as StoredValue[]) {
                if (v.key === valueKey) { this.valueIds[`${catKey}:${valueKey}`] = v.id; set(v.data); }
            }
        } catch {
            // Kein Leserecht auf diese Kategorie -> bleibt leer.
        }
    }

    private async upsert(catKey: CatKey, key: string, data: unknown): Promise<void> {
        const catId = this.catIds[catKey];
        if (!catId) throw new Error(`Kategorie „${catKey}" fehlt – fehlt das Recht zum Anlegen?`);
        const payload = JSON.stringify({ key, data });
        const idKey = `${catKey}:${key}`;
        const existing = this.valueIds[idKey];
        if (existing) {
            await updateCustomDataValue(catId, existing, { value: payload } as any, this.moduleId);
        } else {
            const created = await createCustomDataValue(
                { dataCategoryId: catId, value: payload } as any,
                this.moduleId,
            );
            this.valueIds[idKey] = (created as any).id;
        }
    }

    /**
     * Laedt NUR das Lebenszeichen neu. Die Extension ruft das regelmaessig auf:
     * Sonst waere der Wert so alt wie der Seitenaufruf und das Warnbanner
     * erschiene zwangslaeufig, sobald die Seite ein paar Minuten offen ist.
     */
    async loadGatewayStatus(): Promise<GatewayStatus | null> {
        const holder: { v: GatewayStatus | null } = { v: null };
        await this.loadFrom('steuerung', 'gatewayStatus', (d) => {
            holder.v = (d ?? null) as GatewayStatus | null;
        });
        return holder.v;
    }

    /**
     * Ereignisse, die der Gateway-Dienst festgehalten hat – neueste zuerst.
     *
     * Liegt wie das Lebenszeichen in „steuerung": Wer das Modul bedienen darf,
     * soll auch sehen, ob die Automatik zwischendurch weg war.
     */
    async loadGatewayEvents(): Promise<GatewayEvent[]> {
        const holder: { v: GatewayEvent[] } = { v: [] };
        await this.loadFrom('steuerung', 'gatewayEvents', (d) => {
            holder.v = Array.isArray(d) ? (d as GatewayEvent[]) : [];
        });
        return holder.v;
    }

    /**
     * Alle gespeicherten Blöcke des Logs – Schlüssel auf Einträge.
     *
     * Eine einzige Abfrage: Die API gibt alle Einträge einer Kategorie
     * zusammen heraus, gleich wie viele Wochen darin liegen.
     */
    private async loadLogBloecke(): Promise<Map<string, LogEntry[]>> {
        const raus = new Map<string, LogEntry[]>();
        const catId = this.catIds['log'];
        if (!catId) return raus;
        try {
            const values = await getCustomDataValues<StoredValue>(catId, this.moduleId);
            for (const v of values as unknown as StoredValue[]) {
                if (!v.key || !istLogSchluessel(v.key)) continue;
                this.valueIds[`log:${v.key}`] = v.id;
                raus.set(v.key, Array.isArray(v.data) ? (v.data as LogEntry[]) : []);
            }
        } catch {
            // Kein Leserecht auf die Kategorie -> bleibt leer.
        }
        return raus;
    }

    /**
     * Das dauerhafte Ereignis-Log – neueste Zeile zuerst, über alle Wochen.
     *
     * Für die Anzeige reichen `LOG_MAX` Zeilen. Zum Herunterladen wird die
     * Grenze aufgehoben: Gespeichert sind mehrere Wochen, und wer eine Datei
     * für den letzten Monat zieht, will sie vollständig.
     */
    async loadLog(max = LOG_MAX): Promise<LogEntry[]> {
        const bloecke = await this.loadLogBloecke();
        return zusammenfuehren([], ([] as LogEntry[]).concat(...bloecke.values()), max);
    }

    /**
     * Hängt Zeilen an das gespeicherte Log an und gibt den neuen Stand zurück.
     *
     * Geschrieben wird je Kalenderwoche ein eigener Eintrag. Das ist keine
     * Ordnungsfrage: Ein einzelner Eintrag mit dem ganzen Log sprengt die
     * 10 000 Zeichen, die ChurchTools zulässt – und dann wird gar nichts mehr
     * gespeichert.
     *
     * Angefasst werden nur die Wochen, für die wirklich etwas dazukommt.
     * Vorher wird frisch gelesen und zusammengeführt, sonst verlöre die zweite
     * offene Seite die Zeilen der ersten.
     */
    async appendLog(neue: LogEntry[]): Promise<LogEntry[]> {
        const bloecke = await this.loadLogBloecke();
        if (neue.length) {
            // Was noch im alten Sammel-Eintrag liegt, wandert in seine Wochen.
            // Danach ist er leer und wird beim Aufräumen entfernt.
            const altbestand = bloecke.get(LOG_ALT) ?? [];
            const angefasst = new Set<string>();
            for (const [wocheKey, zeilen] of nachWochen([...neue, ...altbestand])) {
                const woche = wocheVon(wocheKey);
                // Alle Teile dieser Woche zusammenwerfen und neu verteilen: Die
                // neue Zeile gehört nach vorn, nicht ans Ende des letzten Teils.
                const bisher: LogEntry[] = [];
                const alteTeile: string[] = [];
                for (const [key, liste] of bloecke) {
                    if (key !== LOG_ALT && wocheVon(key) === woche) {
                        bisher.push(...liste);
                        alteTeile.push(key);
                    }
                }
                const zusammen = zusammenfuehren(bisher, zeilen, LOG_MAX);
                const teile = aufteilen(woche, zusammen, LOG_WERT_MAX, LOG_TEILE);
                for (const key of alteTeile) bloecke.delete(key);
                for (const [key, liste] of teile) {
                    bloecke.set(key, liste);
                    angefasst.add(key);
                }
                // Teile, die jetzt überflüssig sind (die Woche schrumpfte nie,
                // aber sie kann sich anders verteilen), werden geleert.
                for (const key of alteTeile) {
                    if (!teile.has(key)) { bloecke.set(key, []); angefasst.add(key); }
                }
            }
            if (altbestand.length) { bloecke.set(LOG_ALT, []); angefasst.add(LOG_ALT); }
            for (const key of angefasst) {
                await this.upsert('log', key, bloecke.get(key) ?? []);
            }
            await this.bloeckeAufraeumen(bloecke, angefasst);
        }
        return zusammenfuehren([], ([] as LogEntry[]).concat(...bloecke.values()), LOG_MAX);
    }

    /**
     * Wirft Wochen weg, die über die Aufbewahrung hinaus sind.
     *
     * Ohne das wüchse die Kategorie unbegrenzt weiter – nicht mehr in der
     * Größe eines Eintrags, aber in ihrer Zahl. Gerechnet wird in Wochen, nicht
     * in Einträgen: Eine Woche mit vier Teilen ist trotzdem eine Woche.
     *
     * Ein Fehlschlag beim Löschen ist kein Drama: Die Zeilen sind gespeichert,
     * nur der Platz bleibt belegt.
     */
    private async bloeckeAufraeumen(bloecke: Map<string, LogEntry[]>, angefasst: Set<string>): Promise<void> {
        const catId = this.catIds['log'];
        if (!catId) return;
        const zuAlt = new Set(wochenNachAlter([...bloecke.keys()]).slice(LOG_WOCHEN));
        for (const key of [...bloecke.keys()]) {
            if (!zuAlt.has(wocheVon(key))) continue;
            // Eine Woche, in die gerade noch geschrieben wurde, bleibt stehen -
            // sonst verschwände dieselbe Zeile im selben Atemzug wieder. Der
            // alte Sammel-Eintrag ist die Ausnahme: Er ist eben geleert worden.
            if (angefasst.has(key) && key !== LOG_ALT) continue;
            const id = this.valueIds[`log:${key}`];
            bloecke.delete(key);
            if (!id) continue;
            try {
                await deleteCustomDataValue(catId, id, this.moduleId);
                delete this.valueIds[`log:${key}`];
            } catch {
                // Kein Löschrecht -> der Eintrag bleibt liegen, ohne Schaden.
            }
        }
    }

    /** Leert das gespeicherte Log (nicht die Ereignisse des Gateways). */
    async clearLog(): Promise<void> {
        const catId = this.catIds['log'];
        const bloecke = await this.loadLogBloecke();
        for (const key of bloecke.keys()) {
            const id = this.valueIds[`log:${key}`];
            if (!catId || !id) continue;
            try {
                await deleteCustomDataValue(catId, id, this.moduleId);
                delete this.valueIds[`log:${key}`];
            } catch {
                // Nicht löschbar -> wenigstens leeren, damit nichts stehen bleibt.
                await this.upsert('log', key, []);
            }
        }
    }

    /**
     * Ergebnis der letzten Update-Prüfung. Liegt in „steuerung", damit EINE
     * Abfrage bei GitHub für die ganze Gemeinde reicht – unauthentifiziert sind
     * nur 60 Abfragen pro Stunde und IP erlaubt.
     */
    async loadUpdateCheck(): Promise<UpdateCheck | null> {
        const holder: { v: UpdateCheck | null } = { v: null };
        await this.loadFrom('steuerung', 'updateCheck', (d) => {
            holder.v = (d ?? null) as UpdateCheck | null;
        });
        return holder.v;
    }

    saveUpdateCheck(check: UpdateCheck) { return this.upsert('steuerung', 'updateCheck', check); }

    /** Zugang zum Postausgang. Nur lesbar, wer Rechte auf „email" hat. */
    async loadEmail(): Promise<EmailConfig | null> {
        const holder: { v: EmailConfig | null } = { v: null };
        await this.loadFrom('email', 'email', (d) => { holder.v = (d ?? null) as EmailConfig | null; });
        return holder.v;
    }

    saveEmail(cfg: EmailConfig) { return this.upsert('email', 'email', cfg); }

    /** Postausgang lesen – der Gateway arbeitet ihn ab und leert ihn. */
    async loadOutbox(): Promise<MailJob[]> {
        const holder: { v: MailJob[] } = { v: [] };
        await this.loadFrom('steuerung', 'outbox', (d) => { holder.v = (d as MailJob[]) ?? []; });
        return holder.v;
    }

    /**
     * Nachricht in den Postausgang stellen.
     *
     * Bewusst lesen-anhaengen-schreiben: Der KV-Store kennt keine Listen, nur
     * einen Wert je Schluessel. Zwei Personen, die im selben Moment absenden,
     * koennten sich damit theoretisch ueberschreiben - bei einem Feedback-
     * Formular ist das hinnehmbar, und der Gateway leert den Ausgang laufend.
     * Es bleiben hoechstens die letzten 20 Nachrichten stehen, damit der Wert
     * nicht unbegrenzt waechst.
     */
    async queueMail(job: MailJob, nurEinmalInnerhalbMs = 0): Promise<boolean> {
        const bisher = await this.loadOutbox();
        // Entprellung über den Postausgang selbst, nicht über den Browser:
        // Sonst schickte jede geöffnete Seite dieselbe Störungsmeldung. Was
        // schon eingestellt ist, sieht jede von ihnen.
        if (nurEinmalInnerhalbMs > 0) {
            const grenze = Date.now() - nurEinmalInnerhalbMs;
            const schonDa = bisher.some((j) => j.subject === job.subject
                && new Date(j.at).getTime() >= grenze);
            if (schonDa) return false;
        }
        await this.upsert('steuerung', 'outbox', [...bisher, job].slice(-20));
        return true;
    }

    saveDevice(device: DeviceConfig) { return this.upsert('steuerung', 'device', device); }
    saveRules(rules: MappingRule[]) { return this.upsert('regeln', 'rules', rules); }

    saveSimulate(on: boolean) {
        this.control.simulate = on;
        return this.upsert('steuerung', 'control', this.control);
    }
    saveDurations(durations: Record<string, number>) {
        this.control.durations = durations;
        return this.upsert('steuerung', 'control', this.control);
    }
}

export function newRule(): MappingRule {
    return {
        id: Math.random().toString(36).slice(2),
        name: 'Neue Regel',
        calendarId: null,
        title: null,
        pgsName: '',
        leadMinutes: 15,
        active: true,
    };
}

/**
 * Uebernimmt gespeicherte Regeln, die noch das Altfeld `category`
 * (Veranstaltungsart) tragen: Der dort eingetragene Text wird als Termin-Titel
 * weiterverwendet. In der Praxis stand dort ohnehin derselbe Text, der auch im
 * Termin steht („Gottesdienst"). Beim naechsten Speichern verschwindet das
 * Altfeld von selbst.
 */
function migrateRules(rules: MappingRule[] | null | undefined): MappingRule[] {
    return (rules ?? []).map((r) => {
        const { category, ...rest } = r;
        return { ...rest, title: r.title ?? category ?? null };
    });
}
