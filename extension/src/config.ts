/**
 * Konfiguration der Glockensteuerungs-Extension.
 * Persistiert im ChurchTools Key-Value-Store (customdatacategories/-values),
 * damit auch der Gateway-Dienst dieselbe Konfiguration lesen kann.
 */
import {
    getOrCreateModule,
    getModule,
    getCustomDataCategory,
    createCustomDataCategory,
    getCustomDataValues,
    createCustomDataValue,
    updateCustomDataValue,
} from './utils/kv-store';

export const EXT_KEY: string = import.meta.env.VITE_KEY;
const CATEGORY = 'settings';

export interface DeviceConfig {
    serial: string;
    devicePw: string;       // GEHEIM – nur in ChurchTools (zugriffsbeschraenkt)
    brokerUrl?: string;     // Standard: wss://hew-voco.de:8084/mqtt
}

export interface MappingRule {
    id: string;             // lokale UUID
    name: string;           // sprechender Name der Regel
    calendarId: number | null;   // optional: nur dieser Kalender
    category: string | null;     // optional: nur diese Veranstaltungsart/Kategorie
    pgsName: string;        // Anzeigename des Sofort-PGS, der ausgeloest wird
    leadMinutes: number;    // Vorlauf: X Minuten vor Terminbeginn ausloesen
    active: boolean;
}

export interface AppConfig {
    device: DeviceConfig | null;
    rules: MappingRule[];
}

interface StoredValue { id: number; key: string; data: unknown }

export class ConfigStore {
    moduleId!: number;
    categoryId!: number;
    private valueIds: Record<string, number> = {};

    /** In DEV wird das Modul bei Bedarf erstellt, in PROD nur geladen. */
    async init(dev: boolean): Promise<void> {
        const mod = dev
            ? await getOrCreateModule(EXT_KEY, 'Glockensteuerung', 'ChurchTools ⇄ VOCO-futura')
            : await getModule(EXT_KEY);
        this.moduleId = mod.id;

        let cat = await getCustomDataCategory<object>(CATEGORY);
        if (!cat) {
            await createCustomDataCategory({
                customModuleId: this.moduleId,
                name: 'Einstellungen',
                shorty: CATEGORY,
                description: 'Geräte- und Mapping-Konfiguration',
            } as any, this.moduleId);
            cat = await getCustomDataCategory<object>(CATEGORY);
        }
        this.categoryId = (cat as any).id;
    }

    async load(): Promise<AppConfig> {
        const values = await getCustomDataValues<StoredValue>(this.categoryId, this.moduleId);
        const cfg: AppConfig = { device: null, rules: [] };
        for (const v of values as unknown as StoredValue[]) {
            this.valueIds[v.key] = v.id;
            if (v.key === 'device') cfg.device = v.data as DeviceConfig;
            if (v.key === 'rules') cfg.rules = (v.data as MappingRule[]) ?? [];
        }
        return cfg;
    }

    private async upsert(key: string, data: unknown): Promise<void> {
        const payload = JSON.stringify({ key, data });
        const existing = this.valueIds[key];
        if (existing) {
            await updateCustomDataValue(this.categoryId, existing, { value: payload } as any, this.moduleId);
        } else {
            const created = await createCustomDataValue(
                { dataCategoryId: this.categoryId, value: payload } as any,
                this.moduleId,
            );
            this.valueIds[key] = (created as any).id;
        }
    }

    saveDevice(device: DeviceConfig) { return this.upsert('device', device); }
    saveRules(rules: MappingRule[]) { return this.upsert('rules', rules); }
}

export function newRule(): MappingRule {
    return {
        id: Math.random().toString(36).slice(2),
        name: 'Neue Regel',
        calendarId: null,
        category: null,
        pgsName: '',
        leadMinutes: 15,
        active: true,
    };
}
