A square image tile for the search grid, with a mono meta footer (dimensions · score). Falls back to a paper-gradient placeholder showing `label` when there's no `src`.

```jsx
<div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(132px,1fr))", gap: 12 }}>
  <Thumbnail label="img_0001" dims="1024×1536" score={0.82} selected />
  <Thumbnail src="/img/0002.webp" dims="832×1216" score={0.74} />
</div>
```
Meta is dimensions only + score — by design, format / alpha are never shown.
