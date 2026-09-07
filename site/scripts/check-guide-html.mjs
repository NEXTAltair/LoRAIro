import { readdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const locales = ['ja', 'en', 'zh-tw', 'zh-cn'];
const chapters = ['index', 'installation', 'projects', 'search', 'annotation', 'editing', 'export', 'troubleshooting', 'cli', 'development'];
const placeholderChapters = ['projects', 'search', 'annotation', 'editing', 'export'];

export async function checkGuideHtml(root) {
  const docs = join(root, 'src/content/docs');
  const errors = [];
  for (const locale of locales) {
    const directory = join(docs, locale);
    const files = await readdir(directory);
    const expected = chapters.map((chapter) => `${chapter}.html`).sort();
    if (files.sort().join() !== expected.join()) errors.push(`${locale}: guide sources must be exactly the expected .html files`);
    for (const chapter of chapters) {
      const path = join(directory, `${chapter}.html`);
      const html = await readFile(path, 'utf8');
      if (!/^<!doctype html>\s*<html\b[\s\S]*<head>[\s\S]*<title>[^<]+<\/title>[\s\S]*<body>[\s\S]*<\/body>\s*<\/html>\s*$/i.test(html)) {
        errors.push(`${locale}/${chapter}: invalid HTML source document`);
      }
      if (/^#{1,6}\s|^```|^\|(?:[^\n]*\|)+$/m.test(html)) errors.push(`${locale}/${chapter}: Markdown syntax remains in HTML source`);
      if (placeholderChapters.includes(chapter)) {
        const figure = html.match(/<figure class="guide-placeholder"[\s\S]*?<\/figure>/);
        if (!figure) {
          errors.push(`${locale}/${chapter}: missing operation example figure`);
          continue;
        }
        const image = figure[0].match(/<img\b[^>]*>/i)?.[0];
        if (image) {
          if (!/\bsrc\s*=\s*(["'])[^"']+\1/i.test(image) || !/\balt\s*=\s*(["'])[^"']+\1/i.test(image) || !/<figcaption>[\s\S]*?<\/figcaption>/i.test(figure[0])) {
            errors.push(`${locale}/${chapter}: image replacement needs src, localized alt text, and a caption`);
          }
        } else if (!/guide-placeholder__frame/.test(figure[0]) || !/1280×720/.test(figure[0]) || !/data-aspect-ratio="16 \/ 9"/.test(figure[0])) {
          errors.push(`${locale}/${chapter}: missing standard operation placeholder`);
        }
      }
    }
    const annotation = await readFile(join(directory, 'annotation.html'), 'utf8');
    if (!/<table>[\s\S]*<thead>[\s\S]*<tbody>/i.test(annotation)) errors.push(`${locale}/annotation: semantic table is missing`);
  }
  if (errors.length) throw new Error(errors.join('\n'));
  return locales.length * chapters.length;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    console.log(`HTML guide sources checked: ${await checkGuideHtml(fileURLToPath(new URL('../', import.meta.url)))} documents.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
