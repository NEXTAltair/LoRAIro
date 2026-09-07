export type GuideDocument = {
  body: string;
  description: string;
  headings: { depth: number; slug: string; text: string }[];
  locale: string;
  order: number;
  slug: string;
  title: string;
};

const sources = import.meta.glob('../content/docs/*/*.html', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const decode = (value: string) => value
  .replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>')
  .replaceAll('&quot;', '"').replaceAll('&#39;', "'");
const text = (value: string) => decode(value.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim());
const attribute = (head: string, name: string) => {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return head.match(new RegExp(`<meta\\s+[^>]*name=["']${escaped}["'][^>]*content=["']([^"']*)["']`, 'i'))?.[1]
    ?? head.match(new RegExp(`<meta\\s+[^>]*content=["']([^"']*)["'][^>]*name=["']${escaped}["']`, 'i'))?.[1];
};

function parse(sourcePath: string, source: string): GuideDocument {
  const [, locale, filename] = sourcePath.match(/docs\/([^/]+)\/([^/]+)\.html$/)?.map((part) => part.replaceAll('\\', '/')) ?? [];
  const head = source.match(/<head>([\s\S]*?)<\/head>/i)?.[1];
  const body = source.match(/<body>([\s\S]*?)<\/body>/i)?.[1];
  const title = head?.match(/<title>([\s\S]*?)<\/title>/i)?.[1];
  const description = head && attribute(head, 'description');
  const order = head && attribute(head, 'guide:sidebar-order');
  if (!locale || !filename || !head || body === undefined || !title || !description || !order) {
    throw new Error(`Invalid guide HTML document: ${sourcePath}`);
  }
  const headings = [...body.matchAll(/<h([2-3])\s+id=["']([^"']+)["'][^>]*>([\s\S]*?)<\/h\1>/gi)]
    .map(([, depth, slug, value]) => ({ depth: Number(depth), slug, text: text(value) }));
  return { body: body.trim(), description: decode(description), headings, locale, order: Number(order), slug: filename, title: text(title) };
}

export const guideDocuments = Object.entries(sources)
  .map(([path, source]) => parse(path.replaceAll('\\', '/'), source))
  .sort((a, b) => a.locale.localeCompare(b.locale) || a.order - b.order);

export function guideFor(locale: string, slug: string) {
  return guideDocuments.find((document) => document.locale === locale && document.slug === slug);
}

export function guideSidebar(locale: string) {
  return guideDocuments.filter((document) => document.locale === locale).map((document) => ({
    label: document.title,
    link: document.slug === 'index' ? '/' : `/${document.slug}/`,
  }));
}
