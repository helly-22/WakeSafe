import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import type { Plugin } from 'vite';

const TEMPLATE_PATH = new URL('./sw.template.js', import.meta.url);

function listFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? listFiles(full) : [full];
  });
}

/**
 * Emits `sw.js` at build time from pwa/sw.template.js, filling in the list of
 * built files plus everything in `public/`, and a cache version derived from
 * their contents so a new build always replaces the old cache.
 */
export function precachePlugin(): Plugin {
  let publicDir = '';

  return {
    name: 'wakesafe-precache',
    apply: 'build',
    // Run after Vite's HTML plugin so index.html (the offline app shell) is in the bundle.
    enforce: 'post',

    configResolved(config) {
      publicDir = config.publicDir;
    },

    generateBundle(_options, bundle) {
      const hash = createHash('sha256');
      const urls: string[] = [];

      for (const [fileName, item] of Object.entries(bundle).sort(([a], [b]) => a.localeCompare(b))) {
        urls.push(`/${fileName}`);
        hash.update(fileName);
        hash.update(item.type === 'asset' ? item.source : item.code);
      }

      if (publicDir) {
        try {
          for (const file of listFiles(publicDir).sort()) {
            const url = `/${relative(publicDir, file).split(sep).join('/')}`;
            if (url.endsWith('/.gitkeep') || urls.includes(url)) continue;
            urls.push(url);
            hash.update(url);
            hash.update(readFileSync(file));
          }
        } catch {
          // No public directory: nothing extra to precache.
        }
      }

      const source = readFileSync(TEMPLATE_PATH, 'utf8')
        .replace('__CACHE_VERSION__', hash.digest('hex').slice(0, 12))
        .replace('__PRECACHE_MANIFEST__', JSON.stringify(urls, null, 2));

      this.emitFile({ type: 'asset', fileName: 'sw.js', source });
    },
  };
}
