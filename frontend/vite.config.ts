import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const base = env.VITE_BASE_PATH || '/';

  return {
    base,
    plugins: [react()],
    server: {
      port: 5173,
    proxy: {
        '/api': `http://localhost:${env.VITE_DEV_PROXY_PORT || '9100'}`,
        '/ws': { target: `ws://localhost:${env.VITE_DEV_PROXY_PORT || '9100'}`, ws: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'index.html'),
          // Own document → own WebGL context. Inline R3F in the monitor page starves
          // next to the full-viewport galaxy canvas and lands on the CSS fallback.
          'momus-eye': resolve(__dirname, 'momus-eye.html'),
          ...(env.MONITOR_SCENE_PROBE === '1'
            ? { 'scene-probe': resolve(__dirname, 'scene-probe.html') }
            : {}),
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: [],
    },
  };
});
