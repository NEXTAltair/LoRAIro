ラベル付きのテキスト入力フィールドである。`multiline` を渡すとテキストエリアとして描画する。フォーカス時にはアクセント色の枠線と柔らかなアクセント色のリングを表示する。

```jsx
<Input label="タグ検索" placeholder="1girl, solo, ..." />
<Input label="スコア" placeholder="0.6 以上" />
<Input multiline rows={3} placeholder="屋外で笑っている1人の女の子" />
```

`label` を省略すると入力コントロール単体で描画する。ネイティブの `input` / `textarea` が持つすべての props を継承する。
