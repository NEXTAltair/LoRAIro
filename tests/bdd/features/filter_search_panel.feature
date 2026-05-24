# language: ja
機能: フィルター検索パネル
  FilterSearchPanelの基本的なフィルタリング機能を検証する。

  # NOTE: Issue #420のFilterSearchPanel分割リファクタ完了後に本格的なBDDシナリオを追加すること

  シナリオ: パイプライン完了後にプログレスバーを非表示にする
    前提 FilterSearchPanelが初期化されている
    もし hide_progress_after_completion を呼び出す
    ならば プログレスバーが非表示になる

  シナリオ: パイプラインエラー時にエラーハンドラーが呼ばれる
    前提 FilterSearchPanelが初期化されている
    もし searchパイプラインエラーが発生する
    ならば エラーハンドラーが呼ばれる
