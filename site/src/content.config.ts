import { defineCollection } from 'astro:content';
import { i18nLoader } from '@astrojs/starlight/loaders';
import { i18nSchema } from '@astrojs/starlight/schema';

export const collections = {
  i18n: defineCollection({ loader: i18nLoader(), schema: i18nSchema() }),
};
