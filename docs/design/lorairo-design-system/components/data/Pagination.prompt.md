検索結果のページングに使うコンポーネントである(ADR 0006)。等幅フォントで表示する件数・範囲、前後移動ボタン、ページ番号で構成し、ページ数が多い場合は `…` で省略する。`onChange(page)` のページ番号は 1 始まりである。

```jsx
<Pagination total={1247} pageSize={48} page={page} onChange={setPage} />
```
