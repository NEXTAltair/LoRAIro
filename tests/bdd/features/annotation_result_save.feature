# language: ja
機能: アノテーション結果の保存と outcome ハンドリング
  AnnotationSaveService は CLI/GUI/API の 3 経路で共有される Qt-free サービスで、
  推論結果を DB に保存し成功・スキップ・エラーを集計する。ADR 0023 Phase 1.5 では
  安全性拒否や空アノテーション outcome を error_records に記録し、次回 WebAPI
  送信前に対象画像を除外することで API 課金と refusal / empty ループを防ぐ。

  シナリオ: 安全性拒否を受けた結果はエラーレコードに記録されスキップされる
    前提 DB に登録済みの画像が 1 件ある
    かつ AnnotationSaveService が初期化されている
    もし その画像に対し "SAFETY_REFUSAL: blocked due to safety policy" の結果を処理する
    ならば エラーレコードに 1 件の "SAFETY_REFUSAL" が記録される
    かつ アノテーションは保存されない

  シナリオ: 過去に拒否された画像は WebAPI 送信対象から除外される
    前提 DB に登録済みの画像が 1 件ある
    かつ AnnotationSaveService が初期化されている
    かつ その画像に未解決の安全性拒否履歴がある
    もし その画像パスを WebAPI 送信前フィルタにかける
    ならば フィルタ結果は空である

  シナリオ: 解決済みの拒否履歴を持つ画像はフィルタを通過する
    前提 DB に登録済みの画像が 1 件ある
    かつ AnnotationSaveService が初期化されている
    かつ その画像に解決済みの安全性拒否履歴がある
    もし その画像パスを WebAPI 送信前フィルタにかける
    ならば フィルタ結果にその画像パスが含まれる

  シナリオ: アノテーション結果が DB に保存され成功・スキップ・エラーが集計される
    前提 AnnotationSaveService がモックリポジトリで初期化されている
    かつ DB に存在する phash が 2 件、存在しない phash が 1 件ある
    もし 3 件の推論結果を保存する
    ならば 保存結果は成功 2 件・スキップ 1 件・エラー 0 件・合計 3 件である
