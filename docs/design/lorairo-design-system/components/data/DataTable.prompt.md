The product table style — paper-shade header, hairline rows, hover + selected tints. Drive it with `columns` and `rows`; use `render` for chips/badges/progress in a cell.

```jsx
<DataTable
  columns={[
    { key: "state", header: "状態", render: r => <Chip kind={r.tone}>{r.state}</Chip> },
    { key: "kind", header: "種別", render: r => <TypeBadge>{r.kind}</TypeBadge> },
    { key: "body", header: "内容" },
    { key: "time", header: "完了時刻", align: "right" },
  ]}
  rows={jobs}
  selectedKey={selected}
  onRowClick={r => select(r.id)}
/>
```
