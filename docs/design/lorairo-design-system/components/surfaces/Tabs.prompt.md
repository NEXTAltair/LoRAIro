The app's top navigation. Active tab = semibold ink label with a 2px accent underline on a paper band.

```jsx
const tabs = [
  { id: "search", label: "検索" },
  { id: "map", label: "マップ" },
  { id: "annotate", label: "アノテーション" },
  { id: "jobs", label: "ジョブ" },
];
<Tabs tabs={tabs} active={tab} onChange={setTab} />
```
Controlled — keep `active` in state. Mirrors the QTabBar QSS.
