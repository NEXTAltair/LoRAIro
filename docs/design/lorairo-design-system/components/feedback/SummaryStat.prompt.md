A KPI tile: small label, large mono value, optional sub line. Used in the summary strips at the top of Jobs / Errors / Results.

```jsx
<SummaryStat label="未解決 unresolved" value="33 件" sub="retry可 31 · 上限到達 2" tone="warn" />
<SummaryStat label="解決済 resolved (7d)" value="318 件" sub="auto-retry 284" tone="ok" />
```
Lay them in a grid of equal columns with a 12px gap.
