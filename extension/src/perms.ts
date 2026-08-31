/**
 * Rechte-Prüfung: liest die ChurchTools-Rechte des aktuellen Nutzers und macht
 * sie PRO KATEGORIE verfügbar. Die Custom-Module-Rechte sind Listen von
 * Kategorie-IDs (`view/edit/create custom data`) – so kann ein Admin in der
 * Rechteverwaltung je Untermenü (= Kategorie) festlegen, wer es sehen bzw.
 * bearbeiten darf.
 *
 * Genutzt werden die VORHANDENEN Rechte des Custom-Modules „Glockensteuerung",
 * keine neu erfundenen. ChurchTools erzwingt dieselben Rechte serverseitig auf
 * den KV-Endpunkten – die UI blendet nur passend aus.
 */
import { churchtoolsClient } from '@churchtools/churchtools-client';
import type { CustomModulePermission } from './utils/ct-types';
import { EXT_KEY } from './config';

export interface Rights {
    isAdmin: boolean;
    /** Kategorie-IDs, die der Nutzer sehen darf. */
    viewCats: number[];
    /** Kategorie-IDs, die der Nutzer bearbeiten/anlegen darf. */
    editCats: number[];
}

const asIds = (x: unknown): number[] =>
    Array.isArray(x) ? x.filter((n): n is number => typeof n === 'number') : [];

export async function loadRights(): Promise<Rights> {
    try {
        const g = await churchtoolsClient.get<Record<string, unknown>>('/permissions/global');
        const core = (g?.churchcore ?? {}) as Record<string, unknown>;
        const isAdmin =
            core['administer custom modules'] === true ||
            core['administer settings'] === true;
        const mod = g?.[EXT_KEY] as CustomModulePermission | undefined;
        const viewCats = [
            ...asIds(mod?.['view custom data']),
            ...asIds(mod?.['view custom category']),
        ];
        const editCats = [
            ...asIds(mod?.['edit custom data']),
            ...asIds(mod?.['create custom data']),
        ];
        return { isAdmin, viewCats, editCats };
    } catch {
        // Rechte nicht lesbar -> sicherer Standard: nichts sichtbar/änderbar
        // (außer dem, was ohnehin für alle offen ist, z. B. Hilfe/Feedback).
        return { isAdmin: false, viewCats: [], editCats: [] };
    }
}
