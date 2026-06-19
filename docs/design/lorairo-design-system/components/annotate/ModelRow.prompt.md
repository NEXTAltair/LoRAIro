A model-picker row: status chip · name · provider badge · mono cost/speed. Hover tints it; `disabled` strikes through discontinued models (kept for history).

```jsx
<ModelRow status={<Chip kind="ok">API ready</Chip>} name="claude-haiku-4-5"
  badge={<TypeBadge>anthropic</TypeBadge>} cost="$0.0011/img · ~0.8s" />
<ModelRow status={<Chip kind="warn">needs key</Chip>} name="gpt-5-mini"
  badge={<TypeBadge>openai</TypeBadge>} cost="$0.0009/img · ~0.7s" />
<ModelRow status={<Chip kind="muted">discontinued</Chip>} name="gpt-4-vision-preview"
  badge={<TypeBadge>openai</TypeBadge>} cost="—" disabled />
```
