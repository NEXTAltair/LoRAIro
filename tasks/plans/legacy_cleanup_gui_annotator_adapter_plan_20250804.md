# レガシークリーンアップ計画書: GUI 層における AnnotatorLibAdapter 直接依存の撤廃 (即時削除方針)

作成日: 2025-08-04
ブランチ: feature/cleanup-legacy
対象範囲: src/lorairo/gui/**
ポリシー: 隔離なし・即時削除、必要箇所は SearchFilterService 経由に統一

1. 背景と目的
- GUI ウィジェット層に AnnotatorLibAdapter を直接参照・呼び出す経路が残存しており、SearchFilterService を正とする設計に反する。
- レガシー経路の即時削除により依存関係を単純化し、不具合リスクと重複責務を低減する。

2. 調査サマリ（serena 検索結果より）
- 直接依存/警告ログを確認した主なファイル:
  - src/lorairo/gui/widgets/annotation_control_widget.py
    - import: from ...services.annotator_lib_adapter import AnnotatorLibAdapter
    - load_models(): "Using AnnotatorLibAdapter directly (deprecated, use SearchFilterService)" 警告分岐あり
    - set_annotator_adapter() により直接アダプタ注入可能
  - src/lorairo/gui/widgets/model_selection_widget.py
    - import: from ...services.annotator_lib_adapter import AnnotatorLibAdapter
    - __init__ に annotator_adapter: AnnotatorLibAdapter | None
    - load_models() で未注入時に "AnnotatorLibAdapter not available" 警告
  - src/lorairo/gui/services/model_selection_service.py
    - import: AnnotatorLibAdapter, __init__ に依存注入あり、未注入時警告/空返却
  - src/lorairo/gui/services/search_filter_service.py
    - import: AnnotatorLibAdapter（バックエンド統合のハブ、残存容認）

3. 方針（PoR: Plan of Record）
3.1 GUI ウィジェットからの直接依存の撤廃（第一優先）
- annotation_control_widget.py
  - AnnotatorLibAdapter の import 削除
  - __init__ の annotator_adapter 引数と self.annotator_adapter フィールド削除
  - set_annotator_adapter() を削除
  - load_models() の "elif self.annotator_adapter:" 以下の後方互換分岐を丸ごと削除
  - SearchFilterService が未設定の場合は空リストを示しログのみ（例: info/warn）
- model_selection_widget.py
  - AnnotatorLibAdapter の import 削除
  - __init__ の annotator_adapter 引数削除、関連フィールド/使用箇所削除
  - load_models() を SearchFilterService 等のサービス注入前提の実装へ単純化（なければ親コーディネータ側が提供）

3.2 GUI サービス整合（第二優先）
- model_selection_service.py
  - ウィジェットからの直接呼び出し前提をなくす。必要なら SearchFilterService への実装移譲を検討。
  - ただし本フェーズでは削除は行わず、呼び出し元の整理後に段階的統合を次フェーズで実施。
- search_filter_service.py
  - GUI の唯一の接点として存続。内部で AnnotatorLibAdapter/Mock を扱うのは許容。

4. 影響範囲とリスク
- ウィジェットコンストラクタのシグネチャ変更（annotator_adapter 削除）に伴い、呼び出し元（ウィンドウやコーディネータ、テスト）の修正が必要。
- テストコードのモック/フィクスチャが adapter 依存である場合の修正。
- 暫定的に SearchFilterService 未配線の画面ではモデル一覧が空となる。UI 上は許容とし、サービス配線までの一時措置。

5. 作業手順
Step A: 準備
- ブランチ作成: feature/cleanup-legacy

Step B: ウィジェット修正
- annotation_control_widget.py: 上記 3.1 の項目を適用
- model_selection_widget.py: 上記 3.1 の項目を適用

Step C: 参照箇所修正
- GUI コントローラ/ウィンドウ/コーディネータからのコンストラクタ引数修正（annotator_adapter の削除）
- 必要に応じて SearchFilterService の注入/配線を追加

Step D: テスト更新
- tests/unit/gui/widgets/**, tests/integration/gui/** でコンストラクタ変更に追従
- 直接アダプタ経路のテストは削除またはサービス経由の検証へ置換

Step E: 実行確認
- 単体/統合テスト実行（ruff/mypy も実行）
- GUI 起動でモデル一覧表示の退行がないことを目視確認（サービス配線済み画面）

6. 受け入れ基準（Acceptance Criteria）
- src/lorairo/gui/widgets 配下に AnnotatorLibAdapter を import するコードがゼロであること
- annotation_control_widget.py から直接アダプタ利用の分岐が完全に削除されていること
- model_selection_widget.py がアダプタに依存しないこと
- 修正に伴うビルド・テストが通ること

7. ロールバック戦略
- 破壊的影響が大きい場合、SearchFilterService に薄いアダプタ連携レイヤを注入して GUI からはサービスのみを参照させる。一時的にも GUI 側にアダプタを再導入しない。

8. 次フェーズ案（本計画外）
- model_selection_service の責務を SearchFilterService に統合して冗長性を削減
- service_container 側の実/Mock 切換えを唯一の注入点として標準化

付録: 参考コード断片（発見ログ）
- annotation_control_widget.py: "Using AnnotatorLibAdapter directly (deprecated, use SearchFilterService)"
- model_selection_widget.py / model_selection_service.py: "AnnotatorLibAdapter not available" 警告
- search_filter_service.py: adapter import は残置（統合ポイント）
