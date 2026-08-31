/**
 * Rechte-Prüfung: leitet aus den ChurchTools-Rechten des aktuellen Nutzers ab,
 * ob er nur sehen/läuten darf oder auch Einstellungen ändern darf.
 *
 * Es werden die VORHANDENEN Rechte des Custom-Modules genutzt (sichtbar in der
 * Rechteverwaltung unter „Glockensteuerung"):
 *   - Sehen + Läuten:            „…sehen (view)"
 *   - Einstellungen ändern:      „Daten in Kategorie bearbeiten/erstellen
 *                                 (edit/create custom data)"
 * Admins mit „administer custom modules" dürfen ebenfalls alles.
 *
 * Wichtig: ChurchTools erzwingt dieselben Rechte serverseitig auf den
 * KV-Endpunkten (customdatavalues). Diese Prüfung blendet die Bedienelemente
 * nur passend aus – der eigentliche Schutz liegt am Server.
 */
import { churchtoolsClient } from '@churchtools/churchtools-client';
import type { CustomModulePermission } from './utils/ct-types';
import { EXT_KEY } from './config';

export interface Rights {
    canView: boolean;
    canEdit: boolean;
}

const nonEmpty = (a: unknown): boolean => Array.isArray(a) && a.length > 0;

export async function loadRights(): Promise<Rights> {
    try {
        const g = await churchtoolsClient.get<Record<string, unknown>>('/permissions/global');
        const core = (g?.churchcore ?? {}) as Record<string, unknown>;
        const isAdmin =
            core['administer custom modules'] === true ||
            core['administer settings'] === true;
        const mod = g?.[EXT_KEY] as CustomModulePermission | undefined;
        const canView = isAdmin || mod?.view !== false;
        const canEdit =
            isAdmin ||
            nonEmpty(mod?.['edit custom data']) ||
            nonEmpty(mod?.['create custom data']) ||
            mod?.['create custom category'] === true;
        return { canView, canEdit };
    } catch {
        // Rechte nicht lesbar -> sicherer Standard: sehen ja, ändern nein.
        return { canView: true, canEdit: false };
    }
}
