import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { precachePlugin } from './pwa/precachePlugin.ts';

// The app runs on typed mock fixtures by default (VITE_USE_MOCKS, see .env.example),
// so no backend proxy is configured yet. precachePlugin generates the PWA service
// worker (dist/sw.js) at build time; it is not active in `vite dev`.
export default defineConfig({
  plugins: [react(), precachePlugin()],
  server: { port: 5173 },
});
