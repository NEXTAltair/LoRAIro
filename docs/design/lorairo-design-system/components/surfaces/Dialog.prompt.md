墨スクリム上に表示するモーダルダイアログである。`title`、本文、`footer` で構成し、ESC キー、スクリムのクリック、✕ ボタンで閉じる。`variant="confirm"` を指定すると、キャンセルと OK のフッタを自動生成し、確定時に `onConfirm` を呼び出す。設定画面や `QMessageBox` 相当の確認ダイアログに使用する。

```jsx
<Dialog open={open} onClose={() => setOpen(false)} variant="confirm"
  title="アノテーションを破棄" confirmLabel="破棄" onConfirm={discard}>
  未保存の手動編集が 3 件あります。破棄しますか?
</Dialog>
```
