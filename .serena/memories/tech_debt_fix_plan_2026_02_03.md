# 修正計画メモ（R/E/T再算出ベース）

## 目的
- R/E/Tスコアの高い箇所から順に、可読性・効率・テスタビリティを改善する
- 互換性は考慮しない（安全性と回帰防止のテストは維持）

## 対象スコープ
- src/lorairo + local_packages（tests/docs/examples/prototypes/gui/designer 제외）

## 優先バッチ（High→Medium）
### Batch A（最優先: 12.0以上）
1) local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/webapi_helpers.py (P=13.5)
2) src/lorairo/database/db_repository.py (P=12.0)
3) src/lorairo/gui/workers/annotation_worker.py (P=12.0)
4) local_packages/image-annotator-lib/src/image_annotator_lib/core/registry.py (P=12.0)
5) local_packages/image-annotator-lib/src/image_annotator_lib/core/base/annotator.py (P=12.0)
6) local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/adapters.py (P=12.0)
7) local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py (P=12.0)

### Batch B（次点: 10.5）
- src/lorairo/database/db_manager.py
- src/lorairo/gui/workers/registration_worker.py
- src/lorairo/gui/workers/search_worker.py
- local_packages/image-annotator-lib/src/image_annotator_lib/api.py
- local_packages/image-annotator-lib/src/image_annotator_lib/core/provider_manager.py
- local_packages/image-annotator-lib/src/image_annotator_lib/exceptions/errors.py
- local_packages/image-annotator-lib/src/image_annotator_lib/core/loaders/loader_base.py

### Batch C（Medium: 6.0–9.0）
- src/lorairo/database/schema.py
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/tagger_tensorflow.py
- src/lorairo/services/image_processing_service.py
- src/lorairo/services/ui_responsive_conversion_service.py
- src/lorairo/services/dataset_export_service.py
- src/lorairo/gui/window/main_window.py
- local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_register.py

## 作業順と狙い（各ファイル共通）
1) 長大関数の分割（<=60行目標）
2) UI/IO/DBの責務分離（依存注入可能に）
3) 重い処理のループ内実行や重複計算を除去
4) 既存テストの強化（最低限の回帰ガード）

## 直近の差分レビューで見つかった要調整
- local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_register.py
  - type_id と type_name の不整合を検知できるガード or ログ警告を追加検討
- tests/gui/unit/test_gui_tag_register_service.py
- tests/unit/test_tag_register_service.py
  - 新規追加メソッドの呼び出しを検証するアサーション追加

## 進め方
- Batch Aから着手し、1ファイル完了ごとにR/E/T再評価
- 変更後は対象テストを最小実行し、結果を追記

## 未確定
- 最初に手を入れるファイル順（Batch A内の優先順位）
- テスト範囲（fastのみ or 関連ユニットも実行）
