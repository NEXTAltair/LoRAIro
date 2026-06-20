A dropdown / context menu anchored to a trigger. Clicking the trigger toggles it; ESC or an outside click closes it; selecting a row fires `onSelect` and closes. Use it for the "サムネイル ▾" sort menu, thumbnail right-click actions (skip / duplicate / delete), and row overflow menus.

```jsx
<Menu
  trigger={<Button variant="ghost" size="small">サムネイル ▾</Button>}
  items={[
    { label: "スコア降順", value: "score", glyph: "▾", shortcut: "⌘1" },
    { label: "登録日時", value: "date", glyph: "▸" },
    { separator: true },
    { label: "この画像を skip", value: "skip", glyph: "×", danger: true },
  ]}
  onSelect={(v) => setSort(v)}
/>
```

Items are `{ label, value, glyph, shortcut, disabled, danger }` or `{ separator: true }`. Keep glyphs to the product's functional Unicode set (▾ ▸ × ↺ …) — never emoji. Use `align="right"` when the trigger sits near the right edge, and `open` / `onOpenChange` to control it externally.
