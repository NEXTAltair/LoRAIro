# language: ja
機能: エクスポートフィルタ統合
  DatasetExportService の export_with_criteria() は GUI/CLI/API の統合エントリポイントとして
  criteria または image_ids を受け取り、既存の txt/json エクスポート処理に委譲する。

  シナリオ: criteria 指定でエクスポートが実行される
    前提 DatasetExportService が初期化されている
    かつ DB フィルタが 1 件の画像を返す
    もし criteria を指定して export_with_criteria を呼び出す
    ならば エクスポートが正常に完了する
    かつ db_manager.get_images_by_filter が呼ばれた

  シナリオ: image_ids 指定で DeprecationWarning が発生する
    前提 DatasetExportService が初期化されている
    もし image_ids を指定して export_with_criteria を呼び出す
    ならば DeprecationWarning が発生する
    かつ エクスポートが正常に完了する

  シナリオ: criteria も image_ids も指定しない場合は ValueError
    前提 DatasetExportService が初期化されている
    もし 引数なしで export_with_criteria を呼び出す
    ならば ValueError が発生する

  シナリオ: criteria でフィルタ結果が 0 件の場合は空パスを返す
    前提 DatasetExportService が初期化されている
    かつ DB フィルタが 0 件の画像を返す
    もし criteria を指定して export_with_criteria を呼び出す
    ならば エクスポートが正常に完了する
