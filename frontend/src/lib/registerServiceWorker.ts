/**
 * Registers the generated service worker (dist/sw.js) so the app is installable
 * and works offline. Production builds only: in `vite dev` a service worker would
 * serve stale files and fight hot reload.
 *
 * Updates: a new build installs in the background and takes over on the next
 * load. The page is never reloaded automatically, so in-memory session state is
 * not lost mid-demo.
 */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err: unknown) => {
      console.warn('WakeSafe: service worker registration failed', err);
    });
  });
}
