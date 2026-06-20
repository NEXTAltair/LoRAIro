A labeled range slider — accent groove, a JetBrains-Mono value readout, and optional min/max captions. Use it anywhere the product sets a numeric threshold or score: quality-score filters, manual `quality_score` (0–10) edits, batch sizes. Controlled (`value` + `onChange`) or uncontrolled (`defaultValue`).

```jsx
// quality_score threshold (Search filter)
<Slider label="品質スコア min" min={0} max={10} step={0.5}
  value={q} onChange={setQ} suffix="↑" />

// manual score edit (Tag Edit) — 0–10, two decimals
<Slider label="スコア" min={0} max={10} step={0.1}
  value={score} onChange={setScore}
  minLabel="0.00" maxLabel="10.00" />
```

Pass `format` for custom readouts (percentages, MB). `suffix` appends a unit glyph. Keep to the 0–10 `quality_score` scale (ADR 0029) where it applies.
