ラベル付きチェックボックス。`checked` 塗りは accent、`indeterminate` で – 表示（`checked` が立つと解除）。複数選択（モデルピッカー・フィルタ facet・DataTable の行選択）に使う。

```jsx
<Checkbox label="API モデルのみ" checked={only} onChange={e => setOnly(e.target.checked)} />
<Checkbox label="すべて選択" indeterminate={some && !all} checked={all} onChange={toggleAll} />
<Checkbox label="discontinued を含む" disabled />
```
