The default panel surface — white fill, hairline border, 6px radius. Optional `title` + trailing `aside`.

```jsx
<Card title="フィルタ">…fields…</Card>
<Card title="モデルピッカー" aside={<TypeBadge>multimodal</TypeBadge>}>…rows…</Card>
```
Maps to the QGroupBox / `.card` style. Stack cards with a 12px gap.
