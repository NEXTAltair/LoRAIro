A transient status notification — white card, status-colored left stripe and glyph chip, optional title, message, inline action, and ✕ close. Use it for job completion, save confirmations, and reversible actions (soft-reject undo). Earthy `ok / warn / err / info / neutral` palette; functional glyphs only (no emoji).

```jsx
// auto-dismissing success
<Toast kind="ok" title="保存しました" duration={4000} onClose={dismiss}>
  img_0418 · 変更 5 件を反映
</Toast>

// reversible action, pinned bottom-right
<Toast kind="neutral" floating title="タグを soft-reject"
  action={undo} actionLabel="元に戻す" onClose={dismiss}>
  blurry_background を除外
</Toast>
```

Pass `duration` (ms) to auto-dismiss via `onClose`. `floating` pins it to the app's bottom-right; otherwise it's a plain card you position yourself (stack several in a flex column with `gap`).
