import { createHash } from 'node:crypto';
import { readdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const languages = ['en', 'zh-tw', 'zh-cn'];
export const digest = (text) => createHash('sha256').update(text.replaceAll('\r\n', '\n')).digest('hex');
const codeBlocks = (text) => [...text.replaceAll('\r\n', '\n').matchAll(/<pre\b[^>]*>\s*<code(?:\s[^>]*)?>([\s\S]*?)<\/code>\s*<\/pre>/gi)].map(m => m[1]);
const body = (text) => text.replaceAll('\r\n', '\n').match(/<body>([\s\S]*?)<\/body>/i)?.[1].trim() ?? '';

async function pages(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      for (const child of await pages(join(directory, entry.name))) result.push(`${entry.name}/${child}`);
    } else if (entry.name.endsWith('.html')) result.push(entry.name);
    else throw new Error(`Unexpected content file: ${join(directory, entry.name)}`);
  }
  return result.sort();
}

export async function checkTranslations(root) {
  const content = join(root, 'src/content/docs');
  const sources = await pages(join(content, 'ja'));
  if (!sources.length) throw new Error('Japanese source pages are missing');
  const manifest = JSON.parse(await readFile(join(root, 'translations.json'), 'utf8'));
  if (Object.keys(manifest).sort().join() !== sources.join()) throw new Error('Translation manifest page mismatch');
  for (const language of languages) {
    if ((await pages(join(content, language))).join() !== sources.join()) {
      throw new Error(`${language}: missing or extra pages`);
    }
  }
  for (const page of sources) {
    const source = await readFile(join(content, 'ja', page), 'utf8');
    for (const language of languages) {
      const translation = await readFile(join(content, language, page), 'utf8');
      if (manifest[page][language] !== digest(source)) throw new Error(`${language}/${page}: stale translation`);
      if (body(translation) === body(source)) throw new Error(`${language}/${page}: untranslated Japanese copy`);
      if (JSON.stringify(codeBlocks(translation)) !== JSON.stringify(codeBlocks(source))) {
        throw new Error(`${language}/${page}: code examples differ from Japanese source`);
      }
      if (!/<title>[^<]+<\/title>/i.test(translation)) {
        throw new Error(`${language}/${page}: missing document title`);
      }
    }
  }
  return sources.length;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const count = await checkTranslations(fileURLToPath(new URL('../', import.meta.url)));
    console.log(`Translation freshness: ${count} Japanese pages × ${languages.length} translations checked.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
