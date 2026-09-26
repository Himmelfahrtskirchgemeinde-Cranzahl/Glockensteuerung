import './app.css';
import { createApp } from 'vue';
import { churchtoolsClient } from '@churchtools/churchtools-client';
import App from './App.vue';
import { fitModuleHeight } from './utils/fit-height';
import { themaFolgen } from './utils/thema';

if (import.meta.env.MODE === 'development') {
    import('./utils/reset.css');
}

declare const window: Window & typeof globalThis & { settings?: { base_url?: string } };
const baseUrl = window.settings?.base_url ?? import.meta.env.VITE_BASE_URL;
churchtoolsClient.setBaseUrl(baseUrl);

// Modul-Höhe an den Platz UNTER dem ChurchTools-Header anpassen, damit
// Kopfleiste + Seitenleiste stehen bleiben und nur der Inhalt scrollt.
fitModuleHeight();

// Hell oder dunkel wie ChurchTools. Vor dem Einhängen, damit das Modul
// gleich in der richtigen Farbe erscheint und nicht kurz aufblitzt.
themaFolgen();

createApp(App).mount('#app');
