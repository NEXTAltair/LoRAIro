A status pill with the dot grammar: ● = available, ○ = needs action / inactive. The dot defaults sensibly per `kind`.

```jsx
<Chip kind="ok">installed</Chip>
<Chip kind="ok">API ready</Chip>
<Chip kind="info">実行中</Chip>
<Chip kind="warn">needs key</Chip>
<Chip kind="err">失敗</Chip>
<Chip kind="muted">discontinued</Chip>
<Chip kind="neutral">待機</Chip>
```

Kinds: `ok · warn · err · info · neutral · muted · accent`. Override the dot with `dot="filled|open|none"`.
