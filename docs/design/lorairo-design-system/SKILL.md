---
name: lorairo-design
description: Use this skill to generate well-branded interfaces and assets for LoRAIro (a Japanese desktop tool for preparing image datasets for LoRA / fine-tune training), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `readme.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Orientation

- `readme.md` — the full design guide: product context, content + visual foundations, iconography, manifest.
- `styles.css` + `tokens/` — link `styles.css` and use the CSS custom properties (`var(--accent)`, `var(--paper)`, `var(--font-mono)` …). Never hard-code hex.
- `components/<group>/` — reusable React primitives (Button, Chip, Card, DataTable, Tabs, Thumbnail, StageCard, ModelRow, Terminal …). Each has a `.prompt.md` with a usage example. Read components off `window.LoRAIroDesignSystem_64d8f7` after loading `_ds_bundle.js`.
- `guidelines/` — foundation specimen cards (colours, type, spacing, chip grammar, logo).
- `ui_kits/lorairo-app/` — an interactive recreation of the desktop app; the best reference for how real screens are composed.

## The brand in one breath

Warm paper & ink desktop tool, single terracotta accent, Noto Sans JP + JetBrains Mono, dense multi-pane layout, borders-not-shadows, Japanese-first copy with English identifiers, Unicode-glyph iconography (no emoji, no icon set), one dark surface (the JSONL terminal pane). Numbers everywhere, monospaced. Chip dot grammar: ● available / ○ needs-action.
