# language: ja
機能: お気に入りフィルタの保存と再適用
  FavoriteFiltersService（JSON 永続化）と SearchFilterService（条件構築）を
  横断したフローを仕様化する。保存したフィルタ条件で再検索したとき、
  保存前と同じ検索結果が得られることを検証する。

  責務分離（database_management.feature との非重複）:
  - database_management.feature は DB 登録・検索（Repository 層）のみを扱う。
  - 本 feature は ~/.config/lorairo/favorite_filters.json への JSON 設定
    永続化と、復元した条件での再検索フローを検証する。データストアが異なる。

  注意:
  - FavoriteFiltersService と SearchFilterService に直接の連携コードは無いため、
    dict ⇄ SearchConditions の変換はステップ定義内で明示的に組む。
  - SearchConditions の datetime フィールド（date_range_start/end）は JSON 直列化
    できないため、本 feature のシナリオ対象外とする。保存する filter_dict は
    キーワード・タグロジック・アスペクト比・bool フラグに限定する。
  - 保存先 Path.home() はテストで tmp_path にリダイレクトし、実ユーザー設定を
    汚染しない。

  シナリオ: お気に入りフィルタを保存して再適用すると同じ結果が得られる
    前提 FavoriteFiltersService が一時ディレクトリで初期化されている
    かつ DB フィルタが同一条件に対して常に同じ結果を返す
    もし タグ検索条件を組み立てて "my_favorite" として保存する
    かつ 保存前の検索を実行して結果を記録する
    かつ "my_favorite" を読み込んで検索条件を再構築する
    ならば 保存した条件と復元した条件が一致する
    かつ 復元後の検索結果が保存前の検索結果と一致する
