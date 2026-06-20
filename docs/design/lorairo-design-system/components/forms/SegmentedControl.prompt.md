A bordered segmented toggle for status / mode filters. Options can carry a count badge. Controlled via `value` + `onChange`.

```jsx
<SegmentedControl
  value={status} onChange={setStatus}
  options={[
    { value: "open", label: "未解決", count: 33 },
    { value: "resolved", label: "解決済", count: 318 },
    { value: "ignored", label: "無視", count: 3 },
    { value: "all", label: "すべて", count: 354 },
  ]}
/>
<SegmentedControl value={route} onChange={setRoute} options={["auto", "direct", "openrouter"]} />
```
