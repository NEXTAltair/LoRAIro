# language: ja
機能: タグ検索とフロントエンドフィルタ
  SearchFilterService の UI 入力解析（除外キーワード構文 `-tag`）と
  SearchCriteriaProcessor のフロントエンドフィルタ（アスペクト比・重複除外）の
  振る舞いを仕様化する。

  責務分離（database_management.feature との非重複）:
  - database_management.feature は Repository / DB 層の SQL レベル検索を検証する。
  - 本 feature は GUI サービス層の入力解析と、DB では処理しないメモリ内
    フロントエンドフィルタ（アスペクト比・重複除外）の振る舞いを検証する。
  - 除外タグ（`-tag` 構文）は search_type が "tags" のときのみ有効。
    caption 検索では破棄されるため、シナリオはタグ検索に限定する。

  シナリオ: 除外キーワード付きタグ検索 (-tag 構文)
    前提 SearchFilterService が初期化されている
    もし タグ検索入力 "1girl, -1boy, blue_eyes, -smile" を解析して検索条件を作成する
    ならば 通常キーワードは "1girl, blue_eyes" になる
    かつ 除外キーワードは "1boy, smile" になる
    かつ フィルタ条件の除外タグは "1boy, smile" になる

  シナリオ: アスペクト比フィルタ適用時の件数報告
    前提 SearchCriteriaProcessor が初期化されている
    かつ DB フィルタが幅と高さを持つ 4 件の画像を返す
    もし アスペクト比 "1:1 (正方形)" を指定して検索を実行する
    ならば 報告件数はフィルタ後の件数と一致する
    かつ 報告件数は 2 になる

  シナリオ: 重複画像を除外した検索
    前提 SearchCriteriaProcessor が初期化されている
    かつ DB フィルタが pHash 重複を含む 4 件の画像を返す
    もし 重複除外を有効にして検索を実行する
    ならば 報告件数はフィルタ後の件数と一致する
    かつ 報告件数は 3 になる
