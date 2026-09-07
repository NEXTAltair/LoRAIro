// Run only AFTER translating and reviewing the specified pages. Never called by build/CI.
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { digest, languages } from './check-translations.mjs';

const [language, ...pages] = process.argv.slice(2);
if (!languages.includes(language) || !pages.length || pages.some(p => !/^[a-z-]+\.html$/.test(p))) {
  throw new Error('Usage: node scripts/record-translations.mjs en|zh-tw|zh-cn page.html [...]');
}
const root = fileURLToPath(new URL('../', import.meta.url));
const path = join(root, 'translations.json');
let manifest;
try { manifest = JSON.parse(await readFile(path, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; manifest = {}; }
for (const page of pages) {
  await readFile(join(root, 'src/content/docs', language, page), 'utf8');
  const source = await readFile(join(root, 'src/content/docs/ja', page), 'utf8');
  manifest[page] ??= {};
  manifest[page][language] = digest(source);
}
await writeFile(path, `${JSON.stringify(manifest, null, 2)}\n`);
