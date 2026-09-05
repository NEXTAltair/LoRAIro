import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://nextaltair.github.io',
  base: '/LoRAIro',
  trailingSlash: 'always',
  integrations: [starlight({
    title: 'LoRAIro',
    disable404Route: true,
    defaultLocale: 'ja',
    locales: {
      ja: { label: '日本語', lang: 'ja' },
      en: { label: 'English', lang: 'en' },
      'zh-tw': { label: '繁體中文', lang: 'zh-TW' },
      'zh-cn': { label: '简体中文', lang: 'zh-CN' },
    },
    social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/NEXTAltair/LoRAIro' }],
    editLink: { baseUrl: 'https://github.com/NEXTAltair/LoRAIro/edit/main/site/' },
  })],
});
