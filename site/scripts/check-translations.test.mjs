import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { checkTranslations, digest, languages } from './check-translations.mjs';

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'lorairo-docs-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = '---\ntype: Guide\ntitle: 日本語\n---\n利用方法\n';
  for (const lang of ['ja', ...languages]) {
    const dir = join(root, 'src/content/docs', lang);
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, 'index.md'), lang === 'ja' ? source : `---\ntype: Guide\ntitle: ${lang}\n---\nGuide\n`);
  }
  await writeFile(join(root, 'translations.json'), JSON.stringify({ 'index.md': Object.fromEntries(languages.map(l => [l, digest(source)])) }));
  return { root, source, path: (lang) => join(root, 'src/content/docs', lang, 'index.md') };
}

test('complete translations pass; line endings do not change freshness', async (t) => {
  const f = await fixture(t);
  await writeFile(f.path('ja'), f.source.replaceAll('\n', '\r\n'));
  assert.equal(await checkTranslations(f.root), 1);
});
test('changed Japanese source fails until translations are reviewed', async (t) => {
  const f = await fixture(t);
  await writeFile(f.path('ja'), `${f.source}追加\n`);
  await assert.rejects(checkTranslations(f.root), /stale translation/);
});
test('missing translation fails instead of silently using fallback', async (t) => {
  const f = await fixture(t);
  await rm(f.path('en'));
  await assert.rejects(checkTranslations(f.root), /missing or extra/);
});
test('untranslated copy fails', async (t) => {
  const f = await fixture(t);
  await writeFile(f.path('en'), f.source);
  await assert.rejects(checkTranslations(f.root), /untranslated/);
});
test('translations cannot silently introduce different commands', async (t) => {
  const f = await fixture(t);
  await writeFile(f.path('en'), '---\ntitle: English\n---\n```powershell\ninvalid command\n```\n');
  await assert.rejects(checkTranslations(f.root), /code examples differ/);
});
