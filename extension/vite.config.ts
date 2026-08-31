import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import { execSync } from 'node:child_process';

// Version aus git describe (letzter v-Tag), fällt auf 0.0.0 zurück.
function gitVersion(): string {
    try {
        return execSync("git describe --tags --always --match 'v*'", { encoding: 'utf8' })
            .trim()
            .replace(/^v/, '');
    } catch {
        return '0.0.0';
    }
}

// https://vitejs.dev/config/
export default ({ mode }: { mode: string }) => {
    process.env = { ...process.env, ...loadEnv(mode, process.cwd()) };
    return defineConfig({
        base: `/ccm/${process.env.VITE_KEY}/`,
        plugins: [vue()],
        define: {
            __APP_VERSION__: JSON.stringify(gitVersion()),
        },
    });
};
