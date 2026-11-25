ラベル付きのチェックボックスである。`checked` 状態の塗りはアクセント色、`indeterminate` 状態では `–` を表示する(`checked` が有効になると解除される)。モデルピッカーやフィルタのファセット、`DataTable` の行選択など、複数選択を行う場面で使用する。

```jsx
<Checkbox label="API モデルのみ" checked={only} onChange={e => setOnly(e.target.checked)} />
<Checkbox label="すべて選択" indeterminate={some && !all} checked={all} onChange={toggleAll} />
<Checkbox label="discontinued を含む" disabled />
```
