# language: ja
機能: レーティング/スコア編集
  RatingScoreEditWidget はユーザーが画像の Rating とスコアを編集するウィジェット。
  未設定 Rating は `----` プレースホルダで表示され、保存時にプレースホルダ選択は
  「Rating 変更なし」とみなされ、rating シグナルを発行しない。これにより未設定画像に
  スコアだけを付けたいケースで意図しない Rating が書き込まれることを防ぐ。

  シナリオ: 未設定画像のスコアのみを編集して保存する
    前提 RatingScoreEditWidget が初期化されている
    かつ Rating 未設定の画像をロードする
    もし 保存ボタンをクリックする
    ならば score_changed シグナルが発行される
    かつ rating_changed シグナルは発行されない

  シナリオ: Rating 混在の複数画像でスコアのみ一括編集する
    前提 RatingScoreEditWidget が初期化されている
    かつ Rating が混在した複数画像をバッチ選択でロードする
    もし 保存ボタンをクリックする
    ならば batch_score_changed シグナルが発行される
    かつ batch_rating_changed シグナルは発行されない

  シナリオ: 有効な Rating を選択して保存する
    前提 RatingScoreEditWidget が初期化されている
    かつ 有効な Rating を持つ画像をロードする
    もし 保存ボタンをクリックする
    ならば rating_changed シグナルが発行される
    かつ score_changed シグナルも発行される
