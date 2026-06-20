A token field for editing a tag set — manual annotation tags, query facets, export filters. Tokens render as accent pills with a × affordance; **Enter** or **comma** commits the draft, **Backspace** on an empty draft pops the last token. Controlled via `tags` + `onChange`.

```jsx
const [tags, setTags] = React.useState(["1girl", "solo", "outdoors"]);
<TagInput tags={tags} onChange={setTags} placeholder="手動タグ…" />
```

Values are stored **verbatim (danbooru canonical)** — the field never translates display text; pair it with a separate language selector if you need translated previews. Use `onAdd` / `onRemove` for granular side-effects (e.g. setting `is_edited_manually`). Dedupes by default; pass `allowDuplicates` to keep repeats.
