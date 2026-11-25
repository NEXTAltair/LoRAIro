一時的なステータス通知を表示するコンポーネントである。白いカードに、ステータス色の左ストライプとグリフチップ、任意のタイトル、メッセージ、インラインアクション、✕ の閉じるボタンを備える。ジョブ完了、保存確認、取り消し可能な操作(soft-reject のやり直しなど)に使用する。配色には落ち着いた土色の `ok / warn / err / info / neutral` パレットを用い、絵文字ではなく機能的なグリフのみを使う。

```jsx
// auto-dismissing success
<Toast kind="ok" title="保存しました" duration={4000} onClose={dismiss}>
  img_0418 · 変更 5 件を反映
</Toast>

// reversible action, pinned bottom-right
<Toast kind="neutral" floating title="タグを soft-reject"
  action={undo} actionLabel="元に戻す" onClose={dismiss}>
  blurry_background を除外
</Toast>
```

`duration`(ミリ秒)を指定すると、経過後に `onClose` を呼んで自動で閉じる。`floating` を指定するとアプリの右下に固定表示される。指定しない場合は通常のカードとして描画されるため、配置側で位置を決める(複数並べる場合は `gap` を付けた flex column で縦に積む)。
