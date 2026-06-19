A pipeline stage card: caps label, chosen model, and a status chip. `active` = accent border (focused stage); `shadow` = dashed/italic side-product stage auto-filled by a multimodal model.

```jsx
<StageCard label="TAGGER" model="wd-eva02-large-v3" active
  status={<Chip kind="ok">installed</Chip>} />
<StageCard label="CAPTION" model="claude-haiku-4-5"
  status={<Chip kind="ok">API ready</Chip>} />
<StageCard label="RATING" model="↝ from caption model" shadow />
```
Lay several in a flex row separated by `→` arrows (ink-faint).
