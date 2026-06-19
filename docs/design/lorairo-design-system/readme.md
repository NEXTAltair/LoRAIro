# LoRAIro Design System

A design system distilled from **LoRAIro** — a Japanese desktop tool for preparing image datasets for LoRA / fine-tune training. It automates resize, AI auto-tagging, caption & score generation, and SQLite-backed metadata management, with both a **PySide6 (Qt) GUI** and an agent-friendly **Typer CLI**.

> **Iro (色)** means *colour* in Japanese. The wordmark pairs the LoRA technique with the act of colouring/annotating images — and the brand leans into a warm, papery, "ink on washi" palette rather than the cold blue-grey of typical dev tools.

This is the **codified visual language of the app** — tokens, foundation specimens, reusable React primitives, and an interactive recreation of the desktop UI — so design agents can build branded LoRAIro screens, mocks, slides and prototypes.

---

## Sources

Everything here was reverse-engineered from the product's own design source of truth. Explore these to go deeper:

- **GitHub — [NEXTAltair/LoRAIro](https://github.com/NEXTAltair/LoRAIro)** (MIT). Key files read:
  - `src/lorairo/gui/theme.py` — **Theme v1**: the canonical design tokens + global Qt stylesheet (QSS) generator. The single source of truth for colour/shape/type.
  - `docs/design/theme-v1/hifi-mock.html` — the hi-fi HTML mock the QSS was normalized from (oklch → hex). The visual SSoT.
  - `docs/design/wireframes-v11/` — `HANDOFF.md` + `wireframes-v11.html`, the full screen catalogue and product decisions.
  - `src/lorairo/gui/designer/*.ui` + `widgets/*.py` — the Qt screen layouts.
  - `src/lorairo/cli/` + `docs/cli.md` — the JSONL CLI contract and glyph vocabulary.

> An upload `uploads/LoRAIro-01.zip` was referenced but arrived empty in the workspace — the GitHub repo above was used as the authoritative source instead. If the zip held additional brand assets, re-attach it and I'll fold them in.

---

## Product context

- **One product, one surface**: a single-window **desktop application** (not a website or mobile app). Information-dense, multi-pane, keyboard-driven. Japanese-first UI; English kept for identifiers, schema names, model names, code.
- **Workflow-centric**: a top tab bar moves through the pipeline — **検索 Search → マップ Map → アノテーション Annotate → ジョブ Jobs → 結果 Results → エラー Errors → エクスポート Export → CLI** (⌘1–⌘8).
- **Core loop**: search/filter a dataset → stage images → configure an annotation pipeline (TAGGER → CAPTION → SCORER → RATING → UPSCALE) of local + API models → run as a tracked Job → triage results → export.
- **Two operating faces**: the GUI and a structured, agent-drivable CLI that emits JSONL (`item` / `result` / `error`) on stdout. The dark terminal pane is the one place the warm-paper world goes dark.

---

## Content fundamentals

How LoRAIro writes copy:

- **Japanese-first, English for the technical.** UI chrome, labels, helper text are in Japanese (検索, アノテーション, 実行中, 待機, 失敗). Identifiers stay English/verbatim: model names (`claude-haiku-4-5`, `wd-eva02-large-v3`), schema fields (`is_edited_manually`), job kinds (`model_install`, `provider_batch`), CLI commands. Rule of thumb from the repo: *3+ word English phrases get a Japanese pair; ≤2-word identifiers, schema refs, code and model names stay English.*
- **Terse and factual.** Labels are nouns or noun phrases — "検索結果", "実行中 / キュー", "対象 128 枚（検索から追加）". No marketing voice, no exclamation, no second-person address. The tool states facts and counts.
- **Numbers are first-class and monospaced.** Counts ("1,247 件 / 表示 1–48"), costs ("$0.0011/img · ~0.8s"), progress ("45% (350.0/780.0 MB)"), timestamps ("14:32"), scores ("0.82") are everywhere and always in JetBrains Mono. Use full-width 件/枚 counters in Japanese context.
- **Status as vocabulary.** A small fixed lexicon, reused verbatim: `installed` / `API ready` / `needs key` / `discontinued`; 実行中 / 待機 / 完了 / 失敗 / 中止. Terminal-state words (ADR 0034): FAILED / CANCELED / TERMINATED / UNRESPONSIVE.
- **No emoji.** The only non-text glyphs are functional Unicode symbols (see Iconography). CLI uses ASCII markers `[OK] [--] [!] [i]` instead of ✓✗ to survive Windows cp932.
- **Voice example**: helper line under a model picker — *"○ needs key をクリックすると設定の該当プロバイダ欄が開きます"* (functional, instructive, mixes Japanese guidance with English status term).

---

## Visual foundations

- **Palette — warm paper & ink.** Backgrounds are off-white paper (`--paper #fbfaf6`) and a slightly darker band (`--paper-shade #f1efe6`); cards are pure white. Text is near-black ink with two softer greys. The single accent is a **terracotta / clay** (`--accent #c25e3f`, oklch(0.62 0.14 32)) — used for the primary action, selection, and the active-tab underline. Everything else is the warm neutral scale. This is deliberately *not* a blue dev-tool theme.
- **Status colours** are muted, earthy versions of the usual four: ok = moss green `#3c8a55`, warn = ochre `#b87f1f`, err = brick `#b8402c`, info = slate blue `#3d6f9e`. Each ships as a trio: solid / soft fill / same-family border.
- **One dark surface.** Only the terminal / JSONL pane (`--terminal #23211d`) is dark, with its own syntax palette (key/string/number/boolean). Nothing else inverts.
- **Type.** Body is **Noto Sans JP** (Japanese-first), code & numeric meta is **JetBrains Mono**. Compact desktop scale: 13px base, 11px small, 14/18px headings, 10px mono meta. Handwritten faces (Kalam) used in early wireframes were **dropped** in Theme v1 for this clean modern pairing.
- **Shape.** 6px radius on cards/buttons/inputs, 10px on chips, 3px on small badges, 8px on the outer window. Borders do the separation work: 1px `--line` hairlines everywhere, 2px accent underline for the active tab, 2px accent outline for a selected thumbnail.
- **Spacing.** A strict 4 / 8 / 12 / 16 / 24 scale. Dense, desktop-grade padding (cards pad 12px, inputs 3–6px).
- **Elevation is nearly flat.** The app is borders-not-shadows. The *only* shadow is the floating window shell (`0 2px 10px rgba(26,26,26,.07)`). Plus a translucent ink scrim for loading overlays.
- **Backgrounds** are flat paper fills — no gradients (one tasteful exception: thumbnail placeholder uses a subtle `135deg` paper-shade gradient), no photography, no illustration, no texture. Imagery is the *user's own dataset* shown in square thumbnails — the chrome stays neutral so the images carry all the colour.
- **States.** Hover = tint border + text to accent (buttons), or a paper-shade fill (rows, ghost buttons, thumbnails). Press = accent-soft fill. Focus = accent border + soft accent ring. Selected = accent-soft row / accent outline tile. Disabled = paper-shade fill + faint ink, discontinued models keep a strike-through (history is never deleted).
- **Motion** is minimal and quick: ~0.12s colour/border transitions, ~0.3s progress fills. No bounces, no decorative loops, no parallax. It's a tool, not a show.
- **Chip grammar.** A dot encodes availability: **● = available** (installed / ready / running, ok or info colour) · **○ = needs action or inactive** (needs key = warn, queued = neutral, discontinued = faint). Memorize this — it's used app-wide.

---

## Iconography

LoRAIro has **no icon font, no SVG icon set, and no raster icons** — and no logo image. This is intentional and worth preserving:

- **Logo** is a pure text wordmark: `LoRA` in ink + `Iro` in `--accent`. No mark, no symbol. (See `guidelines/brand-logo.card.html`.)
- **Functional glyphs are plain Unicode**, used sparingly and only where they carry meaning:
  - `⚙` settings gear (titlebar) · `▾` select caret · `→` pipeline stage arrow · `▶` run · `▸` review/expand · `×` remove tag · `●` / `○` status dots · `↝` shadow/auto-acquired stage.
- **CLI markers are ASCII**, not Unicode, to survive Windows cp932 encoding: `[OK]` `[--]` `[!]` `[i]` (source: `src/lorairo/cli/_glyphs.py`).
- **No emoji anywhere.**
- `assets/` is therefore intentionally near-empty — there are no brand binaries to ship. If you need supplementary UI icons for an *extended* mock (folder, search, etc.) that the product itself lacks, reach for a thin-stroke CDN set such as **[Lucide](https://lucide.dev)** and **flag the substitution** to the team — but prefer the Unicode glyphs above for anything that exists in the real app.

---

## Index / manifest

Root:
- **`styles.css`** — the one entry point consumers link. `@import`s the three token files only.
- **`tokens/`** — `colors.css` · `typography.css` (+ Google Fonts import) · `spacing.css`. Base tokens + semantic aliases.
- **`readme.md`** — this guide.
- **`SKILL.md`** — Agent-Skill front matter for use in Claude Code.
- **`assets/`** — intentionally minimal (see Iconography).

Reusable components (`components/<group>/`, namespace `window.LoRAIroDesignSystem_64d8f7`):
- **forms/** — `Button` (default/primary/ghost · base/small), `Input` (+ label, multiline), `Select`.
- **feedback/** — `Chip` (ok/warn/err/info/neutral/muted/accent + dot grammar), `TagChip`, `TypeBadge`, `ProgressBar` (info/ok, striped).
- **data/** — `Card`, `DataTable` (columns/rows, render slots), `Thumbnail` (image tile + mono meta).
- **surfaces/** — `Tabs` (top nav, accent underline), `Terminal` (dark JSONL pane + `.K/.S/.N/.B/.Muted` syntax helpers).
- **annotate/** — `StageCard` (pipeline stage, active/shadow), `ModelRow` (picker row).

Foundation specimen cards (`guidelines/`, shown in the Design System tab): surface / ink & line / accent / status / terminal colours; sans / mono / type-scale; spacing / radii; chip grammar; logo.

UI kit (`ui_kits/lorairo-app/`):
- **`index.html`** — interactive recreation. Click through Search → stage images → Annotate → RUN → Jobs; ⚙ opens Settings. Composes the DS primitives.
- `AppShell.jsx` · `SearchScreen.jsx` · `AnnotateScreen.jsx` · `JobsScreen.jsx`.

---

## Using it

Consumers link the single stylesheet and read components off the bundle namespace:

```html
<link rel="stylesheet" href="styles.css">
<script src="_ds_bundle.js"></script>
<script>
  const { Button, Chip, Card, DataTable, Tabs } = window.LoRAIroDesignSystem_64d8f7;
</script>
```

Reference tokens via CSS custom properties (`var(--accent)`, `var(--paper)`, `var(--font-mono)`) — never hard-code the hex. The `_ds_bundle.js` and `_ds_manifest.json` files are generated by the compiler; don't edit them by hand.

---

> **ローカル取り込みメモ (NEXTAltair):** これは Claude Design プロジェクト "LoRAIro Design System"
> (`64d8f727-6f59-44e6-b3a3-26b89f088b63`) を参照用にミラーしたもの。compiled の
> `_ds_bundle.js` / `_ds_manifest.json` と lint 設定は除外。token は `src/lorairo/gui/theme.py`
> から逆生成されており実テーマと 1:1。Qt 実装の見本として使う(直接組み込み不可)。
