import { createServer } from 'vite';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stringify } from 'yaml';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const server = await createServer({
  root: resolve(root, 'plugins/headlamp-fleet-efficiency'),
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true, entries: [], include: [] },
  appType: 'custom',
});
let fixtures;
try {
  fixtures = await server.ssrLoadModule('/src/demo/fixtures.ts');
} finally {
  await server.close();
}
const { demoRecommendations, demoVpas } = fixtures;
const records = demoRecommendations(new Date('2026-10-30T12:00:00Z'));
for (const [name, values] of [
  ['sample-recommendations.yaml', records],
  ['sample-vpas.yaml', demoVpas(records)],
]) {
  const content =
    '# Synthetic fixtures for 2026-10-30T12:00:00Z. Not approved changes.\n' +
    values.map((value) => stringify(value)).join('---\n');
  const path = resolve(root, 'deploy/headlamp', name);
  if (process.argv.includes('--check')) {
    if (readFileSync(path, 'utf8').replace(/\r\n/g, '\n') !== content)
      throw new Error(`Fixture drift: ${name}`);
  } else {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
}
console.log('Synthetic recommendation and VPA manifests match.');
