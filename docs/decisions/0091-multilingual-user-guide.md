---
type: ADR
title: Japanese-first multilingual user guide on GitHub Pages
status: Accepted
timestamp: 2026-09-05
tags: [documentation, maintenance]
---
# ADR 0091: Japanese-first multilingual user guide

## Context

The user no longer uses Sphinx, but still needs a detailed public user guide on GitHub Pages.
Japanese, English, Traditional Chinese and Simplified Chinese must cover the same instructions.
The maintainer writes Japanese; coding agents assist translation. Developer ADRs remain repository documents.

## Decision

- Maintain the static user guide in `site/` with Astro + Starlight, separate from the Python application.
- Use Japanese source pages and equivalent `en`, `zh-tw`, `zh-cn` files. Clearly identify AI-assisted translations.
- Keep the current `/LoRAIro/` Pages URL. Publish built artifacts with GitHub Actions, not a generated branch.
- Validate builds on Windows and Linux. Use Node.js 24 in CI and the Dev Container.
- Fail builds for missing translations, stale normalized source hashes, copied Japanese bodies or changed code
  examples. Hash recording is an explicit post-translation action, never an automatic build step.
- Validate local output links and the complete locale page set. Review semantic translation quality separately;
  a matching source hash cannot prove a translation is correct.
- Keep API keys, project data and the application runtime out of the documentation build. No paid translation
  API is invoked by CI. Preserve the existing developer documentation/OKF architecture.
- Retire `gh-pages` only after the replacement main deployment succeeds and public locale routes are verified.

## Alternatives and rationale

Keeping Sphinx contradicts the requested retirement and preserves an obsolete generated API catalogue.
Writing a custom site would duplicate navigation, localized controls and search. Starlight provides those
features directly, including locale routing; the only project-specific tooling is translation freshness and
output-link validation. MkDocs is viable, but changing the already selected Starlight approach provides no
required capability that justifies introducing another documentation design.

## Consequences

Node is required to author/build documentation, not to run the Python application. All four translations
must accompany a Japanese change before publication. The public guide documents supported behavior, not
every internal class. Guide languages are distinct from application UI languages and exported tag languages.

## References

- [Authoring and deployment](../../site/README.md)
- [Starlight internationalization](https://starlight.astro.build/guides/i18n/)
- [Astro GitHub Pages deployment](https://docs.astro.build/en/guides/deploy/github/)
