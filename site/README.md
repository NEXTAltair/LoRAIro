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

1. Edit the full HTML document at `src/content/docs/ja/<page>.html` and verify instructions against current application code. HTML is the canonical guide source: use semantic elements such as `h2`, `p`, `ol`, `table`, `thead`, `tbody`, `th`, `td`, and `pre`/`code`; do not add Markdown or MDX guide bodies.
2. Ask a coding agent to translate the changed HTML document into `en`, `zh-tw`, and `zh-cn` with the same filename.
3. Review warnings, numbers, links and CLI arguments against Japanese. Keep `pre`/`code` contents verbatim.
   Do not confuse guide languages with GUI translation or exported tag languages. Do not invent UI controls.
4. Only after each translation is complete, record its source revision:

   ```text
   node scripts/record-translations.mjs en export.html
   node scripts/record-translations.mjs zh-tw export.html
   node scripts/record-translations.mjs zh-cn export.html
   ```

5. Run tests and build; commit translations and `translations.json` together.

`check-translations.mjs` compares normalized source SHA-256 hashes, page sets, HTML `pre`/`code` examples and untranslated copies. `check-guide-html.mjs` verifies the canonical HTML documents, semantic tables and the operation placeholders.
It fails for missing or stale translations instead of relying on Starlight's Japanese fallback.
Hashes demonstrate source revision tracking, not semantic translation quality; agent review remains necessary.
Never run the recording command just to silence a freshness failure. No paid translation service is called by CI.

`check-build.mjs` verifies all 40 locale pages and local generated links under the `/LoRAIro/` base.
When intentionally adding/removing a chapter, update its expected count along with all four languages.

## Publication migration

After the PR is ready and approved, configure this repository's Pages build type as GitHub Actions.
Verify a successful main deployment and HTTP responses for all four language homepages before retiring
the old `gh-pages` branch. Its historical commit remains recoverable through Git history.

## Operation example image placeholders

The `projects`, `search`, `annotation`, `editing`, and `export` chapters include a localized
`figure.guide-placeholder` immediately beside the relevant GUI procedure. It intentionally has no
`img` element or `src` while the screenshot is pending, so it cannot create a broken-image request.
The default frame is 1280×720 (16:9) and stays within the article width.

To replace a placeholder, preserve the `figure` and `figcaption`, replace the inner `div` with an
image, and provide localized alternative text. For example:

```html
<figure class="guide-placeholder" style="--guide-placeholder-ratio: 4 / 3">
  <img src="/LoRAIro/images/export-settings.png" alt="Export format and resolution settings">
  <figcaption>Export settings (1280×960)</figcaption>
</figure>
```

Set `--guide-placeholder-ratio` to the image’s intended ratio (for example `4 / 3`) when the
default 16:9 ratio is unsuitable. Add the real image under `site/public/`, use its `/LoRAIro/`
URL, keep `max-width: 100%`, and use `height: auto` on the image so it is not cropped. Update all
four localized HTML documents and their captions/alternative text, review the translations, then
record their translation hashes.

References: [Starlight i18n](https://starlight.astro.build/guides/i18n/),
[Astro GitHub Pages deployment](https://docs.astro.build/en/guides/deploy/github/).
