A text button — bordered by default, accent-filled `primary` for the one main action per view, transparent `ghost` for toolbar actions.

```jsx
<Button variant="primary">検索</Button>
<Button>クリア</Button>
<Button size="small" variant="ghost">サムネイル ▾</Button>
<Button variant="primary" disabled>RUN PIPELINE ▶</Button>
```

Variants: `default` · `primary` · `ghost`. Sizes: `base` · `small`. Hover tints border + text to accent (default), darkens (primary), or shows a paper-shade fill (ghost). Use exactly one `primary` per screen.
