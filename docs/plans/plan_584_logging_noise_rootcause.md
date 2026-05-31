# Plan #584: DEBUG ログ過剰の解消 + root-cause 冗長処理修正

- **対象 Issue**: [NEXTAltair/LoRAIro#584](https://github.com/NEXTAltair/LoRAIro/issues/584)
- **策定日**: 2026-05-31
- **スコープ**: ログ整理 + root-cause perf 修正（両方を #584 で実施 / ユーザー確定）
- **ログ方針**: TRACE レベル導入 + per-item 診断を TRACE 降格（ユーザー確定）
- **関連 ADR**: 0021 (litellm registry), 0030 (model selection UI), 0043 (db_core loguru 統一), 0045 (large search log level)

## 1. 問題定義と成功基準

### 問題
`logs/lorairo.log` の DEBUG が 91.8%（6,741/7,339 行）。大半は (a) オブジェクト初期化スパム、(b) 正常系の毎回確認ログ、(c) per-item 診断ログ。デバッグ用途として DEBUG を有効にしても本来の診断情報が埋もれる。

ログ過多は**症状**であり、その下に 2 つの冗長処理（root cause）が存在する:
1. モデルチェックボックスの全消し全再生成（起動時 2〜3 回の冗長 rebuild × 2 インスタンス = 698 inits）
2. サムネイル描画の O(n²) 線形スキャン + パス解決の無キャッシュ重複解決

### 成功基準
- [ ] 同等操作（起動 + 75 枚選択/表示）で DEBUG が「操作単位の有用情報」中心になり、行数が大幅減（model_checkbox 由来 ~2,792 行 + 正常系 ~671 行を 0 に）
- [ ] `TRACE` レベルが config (`[log]` / `[log.levels]`) で有効化可能になり、per-item firehose は TRACE でのみ出力
- [ ] モデルチェックボックスが同一フィルタ結果で再構築されない（起動時 rebuild 回数が減る）
- [ ] `get_image_by_id` が O(1)、`resolve_stored_path` が同一入力で重複解決しない
- [ ] `.claude/rules/logging.md` に DEBUG/TRACE ポリシーを反映、ADR 化
- [ ] CI-equivalent filter 全 pass、GUI 回帰なし

## 2. ライブラリ調査結果（Agent Teams）
`image-annotator-lib` は別 sink (`logs/image-annotator-lib.log`, 1.5KB) で **lorairo.log のノイズ源ではない**。ADR 0043 のとおり外部ライブラリの標準 logging は loguru に集約されていない。今回の 6,741 行はすべて LoRAIro 本体由来。→ ライブラリ側の修正は不要。

## 3. ロギング基盤の現状
- `utils/log.py` は `[log.levels]` でモジュール別レベル制御を**既にサポート**（`_level_filter` が最長一致プレフィックスで判定）。
- `LEVEL_NAME_TO_NO` に **`TRACE` 未登録**。loguru の TRACE は level.no=5。
- sink は `level=0` でフィルタ関数に委譲しているため、`TRACE` を map に追加すれば config から有効化可能。

## 4. 実装計画（4 パート）

### Part A: TRACE インフラ整備
- **A1** `utils/log.py`: `LEVEL_NAME_TO_NO` に `"TRACE": 5` を追加。
- **A2** `.claude/rules/logging.md`: TRACE レベル定義を追加し DEBUG 定義を改訂。
  - DEBUG = 「操作・コンポーネント単位の診断（per-operation）」
  - TRACE = 「per-item の大量詳細（パス解決・annotation 整形・1 件ごとのループ詳細）」
- **A3** ADR 新規（0046）: "TRACE Level for Per-Item Diagnostics" でポリシー変更を記録。README インデックス更新。

### Part B: 不要ログの削除（規約違反・正常系確認）
- **B1** `gui/widgets/model_checkbox_widget.py`: 初期化スパム削除
  - L120 `__init__` "initialized"、L159 `_setup_model_display`、L186 `_apply_provider_styling`、L195 `_setup_connections`
  - L205/L218（selection changed）は TRACE 降格（user 操作応答だが per-widget 多発のため）
- **B2** `gui/state/dataset_state.py:369-371`: 「正常な状態」DEBUG を削除（異常系 L377 WARNING / L383 not-found は維持）
- **B3** `services/model_selection_service.py:66-70`: per-model ループ DEBUG「モデル読込」を削除（INFO サマリ L63 は維持）

### Part C: per-item 診断の TRACE 降格
- **C1** `database/db_core.py:194, 200`: `logger.debug` → `logger.trace`（パス解決）
- **C2** `database/repository/image.py:1559-1565`: → `logger.trace`（Formatted annotations）
- **C3** `gui/widgets/rating_score_edit_widget.py`: L73 `__init__` "called" 削除、L178/L216 populate を `logger.trace`
- **C4** 75 枚選択で各 75 行出る per-selection 系（`selected_image_details_widget` / `annotation_data_display_widget` / `image_preview` / `thumbnail._on_state_current_image_changed`）を精査し per-item は TRACE 降格

### Part D: root-cause perf 修正（回帰リスク高 → テスト必須）
- **D1 モデル rebuild 抑制** `gui/widgets/model_selection_widget.py:update_model_display`
  - options 計算を `_clear_model_display` の**前**に移動し、フィルタ結果シグネチャ（`litellm_model_id` 列 + mode + route_preference + available_providers + selection state）をキャッシュ。前回と同一なら clear+rebuild をスキップ。
  - `_update_batch_capable_display` (L750/824 系) にも同様のガード。
  - 起動時の冗長連鎖（`widget_setup_service.py:397` の即時 apply_filters）は、skip ガードにより同一結果の 2〜3 回目が自動的に no-op 化される。連鎖そのものの整理は影響大のため**今回は skip ガードで吸収**（初期化順序の改変は避ける）。
- **D2 get_image_by_id O(1) 化** `gui/state/dataset_state.py`
  - `_image_index: dict[int, dict]` を導入。`_all_images` / `_filtered_images` を設定する全 setter（set_all_images / set_filtered / 検索結果更新 L223 / `update_image_metadata`）でインデックスを再構築/更新。
  - `get_image_by_id` を線形スキャンから dict ルックアップへ。`_display_page` の per-thumbnail 呼び出しが O(n²)→O(n)。
- **D3 resolve_stored_path キャッシュ** `database/db_core.py`
  - **project root は可変**（マルチプロジェクト切替）。`(project_root, stored_path)` をキーにした module-level dict キャッシュにする。`@lru_cache(stored_path)` 単独は stale パスを返すため**不可**。
  - project 切替契機（`get_current_project_root` の更新箇所）でキャッシュ clear を呼ぶフックを追加。
  - **最高リスク項目** → project 切替の単体テスト必須。

## 5. テスト戦略
- **Unit (`-m unit`)**
  - `tests/unit/utils/test_log.py`: config `level="TRACE"` で `default_level_no==5`、TRACE record が pass / DEBUG 既定では filter される。`[log.levels]` でモジュール別 TRACE 有効化。
  - `tests/unit/gui/state/test_dataset_state.py`: `get_image_by_id` の O(1) インデックス、各 setter / `update_image_metadata` 後の整合、filtered フォールバック、未登録時 None。
  - `tests/unit/database/test_db_core.py`: `resolve_stored_path` キャッシュヒット、**project root 切替時の invalidation**、絶対パス/プレフィックス正規化分岐。
- **GUI (`-m gui`, pytest-qt, QT_QPA_PLATFORM=offscreen)**
  - `model_selection_widget`: 同一フィルタ再適用 → `_add_provider_group` が再呼びされない（rebuild skip）/ フィルタ変更 → rebuild される。`qtbot.waitUntil` 使用、QMessageBox は monkeypatch。
- **回帰検証**: 代表フロー実行後、DEBUG レベルで model_checkbox / 正常系ログが出ないこと、TRACE レベルで per-item が出ることを確認。
- **CI-equivalent filter**（PR 前必須、`.claude/rules/testing.md`）:
  `.venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60`

## 6. リスクと対策
| リスク | 深刻度 | 対策 |
|---|---|---|
| `resolve_stored_path` キャッシュが project 切替で stale パスを返す | 高 | `(project_root, stored_path)` キー + 切替時 clear + 単体テスト |
| rebuild skip ガードのシグネチャ漏れで UI が stale | 中 | selection/availability/route_preference/mode を全て署名に含める + GUI テスト |
| `_image_index` が mutation パスと不整合 | 中 | 全 setter でインデックス再構築、`update_image_metadata` で同期、単体テスト |
| TRACE level=5 と loguru の不整合 | 低 | loguru TRACE.no==5 を前提、log.py 単体テストで検証 |
| ログ削除でデバッグ情報喪失 | 低 | 削除は「正常系確認/オブジェクト初期化」のみ。診断価値ある per-item は TRACE で温存 |

## 7. 実装順序
1. **Part A**（TRACE インフラ）→ TRACE 降格の前提
2. **Part B**（削除）+ **Part C**（TRACE 降格）→ 即効でノイズ除去、低リスク
3. **Part D1**（rebuild skip）→ GUI テスト
4. **Part D2**（index）→ unit テスト
5. **Part D3**（path cache）→ unit テスト（最高リスク、最後）
6. ADR 0047 記述 + logging.md 更新（Part A と並行可）
7. CI-equivalent filter 全 pass 確認 → PR

## 8. 影響範囲
- Service 層: `model_selection_service`（ログ削除のみ）
- GUI: `model_selection_widget`(D1), `dataset_state`(B2/D2), `model_checkbox_widget`(B1), `rating_score_edit_widget`(C3), thumbnail 系 per-selection(C4)
- DB: `db_core`(C1/D3), `repository/image`(C2)
- config: `config/lorairo.toml` は変更不要（TRACE は任意で `[log.levels]` に指定可能、デフォルトは現状維持）
- スキーマ変更: なし / マイグレーション: 不要 / 依存追加: なし

## 9. implement への引き継ぎ
- ブランチ: `fix/issue-584`（git-workflow.md 準拠、worktree は `/tmp/worktrees/`）
- TDD（superpowers:test-driven-development）で Part D は test 先行
- 完了時 ADR 0047 + logging.md 更新を忘れない
