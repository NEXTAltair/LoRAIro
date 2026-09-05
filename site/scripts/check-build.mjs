import { readdir, readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../dist/', import.meta.url));
const base = new URL('https://nextaltair.github.io/LoRAIro/');
async function htmlFiles(dir) {
  const files = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await htmlFiles(path));
    else if (entry.name.endsWith('.html')) files.push(path);
  }
  return files;
}
await stat(join(root, 'index.html'));
const errors = [];
const files = await htmlFiles(root);
for (const file of files) {
  const relative = file.slice(root.length).replaceAll('\\', '/');
  const url = new URL(relative.replace(/index\.html$/, ''), base);
  const html = await readFile(file, 'utf8');
  for (const [, raw] of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const target = new URL(raw.replaceAll('&amp;', '&'), url);
    if (target.origin !== base.origin || !['http:', 'https:'].includes(target.protocol)) continue;
    if (!target.pathname.startsWith(base.pathname)) { errors.push(`${relative}: outside Pages base: ${raw}`); continue; }
    const local = decodeURIComponent(target.pathname.slice(base.pathname.length));
    const path = resolve(root, local.endsWith('/') || !local ? `${local}index.html` : local);
    try { if (!(await stat(path)).isFile()) throw new Error('not a file'); }
    catch { errors.push(`${relative}: missing target ${raw}`); }
  }
}
for (const lang of ['ja', 'en', 'zh-tw', 'zh-cn']) {
  const pages = await htmlFiles(join(root, lang));
  if (pages.length !== 10) errors.push(`${lang}: expected 10 pages, found ${pages.length}`);
}
if (errors.length) throw new Error(errors.join('\n'));
console.log(`Built pages and local links checked: ${files.length} HTML files.`);
