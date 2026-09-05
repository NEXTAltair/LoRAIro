# LoRAIro user guide

GitHub Pages: https://nextaltair.github.io/LoRAIro/

This is the user-facing guide, separate from developer ADRs and specifications in `docs/`.
Astro + Starlight provides static pages, search and Japanese/English/Traditional Chinese/Simplified Chinese navigation.
The existing GitHub Pages URL is retained; deployment uses Actions, not the old Sphinx `gh-pages` branch.

## Build on Windows or Linux

Node.js 24 is used in CI. No Python, GPU, project DB, API keys or Kit installation is needed.

```text
cd site
npm ci
npm test
npm run build
npm run preview
```

For authoring, use `npm run dev`. Search is generated during the production build.
Only `site/dist` is uploaded. PRs validate both OSes but never publish. Main publishes after both builds pass.

## Japanese-first translation workflow

1. Edit `src/content/docs/ja/<page>.md` and verify instructions against current application code.
2. Ask a coding agent to translate the changed page into `en`, `zh-tw`, and `zh-cn` with the same filename.
3. Review warnings, numbers, links and CLI arguments against Japanese. Keep code blocks verbatim.
   Do not confuse guide languages with GUI translation or exported tag languages. Do not invent UI controls.
4. Only after each translation is complete, record its source revision:

   ```text
   node scripts/record-translations.mjs en export.md
   node scripts/record-translations.mjs zh-tw export.md
   node scripts/record-translations.mjs zh-cn export.md
   ```

5. Run tests and build; commit translations and `translations.json` together.

`check-translations.mjs` compares normalized source SHA-256 hashes, page sets, code examples and untranslated copies.
It fails for missing or stale translations instead of relying on Starlight's Japanese fallback.
Hashes demonstrate source revision tracking, not semantic translation quality; agent review remains necessary.
Never run the recording command just to silence a freshness failure. No paid translation service is called by CI.

`check-build.mjs` verifies all 40 locale pages and local generated links under the `/LoRAIro/` base.
When intentionally adding/removing a chapter, update its expected count along with all four languages.

## Publication migration

After the PR is ready and approved, configure this repository's Pages build type as GitHub Actions.
Verify a successful main deployment and HTTP responses for all four language homepages before retiring
the old `gh-pages` branch. Its historical commit remains recoverable through Git history.

References: [Starlight i18n](https://starlight.astro.build/guides/i18n/),
[Astro GitHub Pages deployment](https://docs.astro.build/en/guides/deploy/github/).
