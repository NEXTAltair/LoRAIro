トリガー要素を起点に開くドロップダウン/コンテキストメニューである。トリガーをクリックすると開閉が切り替わり、ESC キーまたはメニュー外のクリックで閉じる。項目を選択すると `onSelect` を発火して閉じる。「サムネイル ▾」の並び替えメニュー、サムネイルの右クリック操作(skip / duplicate / delete)、行のオーバーフローメニューなどに使用する。

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

各項目には `{ label, value, glyph, shortcut, disabled, danger }` または `{ separator: true }` を指定する。グリフにはプロダクトの機能的な Unicode 記号(`▾ ▸ × ↺ …`)のみを用い、絵文字は使わない。トリガーが右端にある場合は `align="right"` を指定し、外部から開閉を制御する場合は `open` と `onOpenChange` を使う。
