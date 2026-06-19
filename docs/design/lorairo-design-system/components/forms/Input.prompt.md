A labelled text field. Pass `multiline` for a textarea. Focus draws the accent border and a soft accent ring.

```jsx
<Input label="タグ検索" placeholder="1girl, solo, ..." />
<Input label="スコア" placeholder="0.6 以上" />
<Input multiline rows={3} placeholder="屋外で笑っている1人の女の子" />
```

Omit `label` to render the bare control. Inherits all native input/textarea props.
