件数・範囲（mono）+ 前後ボタン + ページ番号（多ページは … で省略）。`onChange(page)` は 1 始まり。検索結果のページングに使う（ADR 0006）。

```jsx
<Pagination total={1247} pageSize={48} page={page} onChange={setPage} />
```
