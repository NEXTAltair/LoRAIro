墨スクリム上のモーダル。`title` / 本文 / `footer`、ESC・スクリムクリック・✕ で閉じる。`variant="confirm"` で キャンセル + OK フッタを自動生成（`onConfirm`）。設定や QMessageBox 相当の確認に使う。

```jsx
<Dialog open={open} onClose={() => setOpen(false)} variant="confirm"
  title="アノテーションを破棄" confirmLabel="破棄" onConfirm={discard}>
  未保存の手動編集が 3 件あります。破棄しますか？
</Dialog>
```
