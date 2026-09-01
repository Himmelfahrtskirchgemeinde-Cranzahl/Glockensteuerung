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
} from './utils/kv-store';

export const EXT_KEY: string = import.meta.env.VITE_KEY;

/** Untermenü = Kategorie. shorty ist stabil (erscheint in der Rechteverwaltung). */
export const CATS = [
    { key: 'steuerung', shorty: 'steuerung', name: 'Steuerung', desc: 'Live-Steuerung / Läuten' },
    { key: 'log', shorty: 'ereignislog', name: 'Ereignis-Log', desc: 'Ereignis-Log' },
    { key: 'regeln', shorty: 'regeln', name: 'Automatik-Regeln', desc: 'Termin → Programm' },
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

/** Lebenszeichen des Gateway-Dienstes (vom Gateway geschrieben, hier nur gelesen). */
export interface GatewayStatus {
    at: string;              // ISO-Zeitstempel des letzten Lebenszeichens
    rules?: number;          // wie viele Regeln der Dienst geladen hat
    simulation?: boolean;    // laeuft der Dienst im Simulationsmodus?
    device?: string | null;  // Seriennummer, die er nutzt
}

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
