# genai-tag-db-tools GUI リファクタリング計画（2025-12-23）

## 計画概要

**プランID**: immutable-tumbling-quokka
**作成日**: 2025-12-23
**対象**: genai-tag-db-tools GUI層の完全リファクタリング
**実施範囲**: Phase 1-4 すべて実施（ユーザー決定）
**総所要時間**: 15-21時間（2-3日）

## ユーザー要件

### 実施スコープ（確認済み）
✅ **Phase 1-4 すべて実施**（完全リファクタリング）
- 最も品質が高く、技術的負債ゼロの状態を実現
- カバレッジ75%達成を含む

### 統合状況（確認済み）
✅ **完全に独立したアプリケーション**
- genai-tag-db-tools は独立ツールとして動作
- LoRAIro 本体への影響なし
- リファクタリングの影響範囲は genai-tag-db-tools 内に限定

## 目標

1. **コード品質向上**: print()文削除、型ヒント追加、Ruff 100%準拠
2. **アーキテクチャ統一**: core_api 完全統合（全サービス）
3. **テスト拡充**: Widget層 pytest-qt テスト 15+ 件（カバレッジ75%）
4. **パフォーマンス改善**: UI スレッドブロッキング解消（非同期化）
5. **保守性向上**: サービスライフサイクル管理、初期化パターン統一

## 現状分析

### GUI 構造
```
gui/ (総コード量: ~2,400行 + 自動生成UIファイル)
├── windows/main_window.py          (181行)
├── widgets/                        (561行)
│   ├── tag_search.py               (150行) - 検索Widget
│   ├── tag_register.py             (106行) - 登録Widget
│   ├── tag_statistics.py           (196行) - 統計Widget
│   ├── tag_cleaner.py              (51行)  - クリーナーWidget
│   └── controls/log_scale_slider.py (58行)
├── services/                       (689行)
│   ├── db_initialization.py        (243行)
│   └── app_services.py             (446行) - 4サービス
├── presenters/                     (224行)
├── converters.py                   (65行)
└── models/dataframe_table_model.py (54行)
```

### core_api 統合状況
- ✅ TagSearchService: 完全統合済み
- ⚠️ TagStatisticsService: `get_general_stats()` のみ統合
- ❌ TagRegisterService: Repository 直接アクセス
- ❌ TagCleanerService: legacy TagSearcher 使用

### 主要問題点
1. **コード品質**: print() 文残存、型ヒント不足
2. **サービス初期化**: Widget間で不統一なパターン
3. **UI ブロッキング**: 大規模検索（1000+件）でフリーズ
4. **テスト不足**: Widget層のテスト 0 件

## 実装計画（4フェーズ）

### Phase 1: コード品質改善（2-3時間）
1. print() 文削除 → logger 統一
2. 型ヒント追加（全 Widget の set_service() 等）
3. Ruff lint/format 全適用
4. エラーハンドリング改善（具体的な例外型）

**対象ファイル**:
- gui/widgets/*.py（全5ファイル）
- gui/presenters/*.py（全3ファイル）
- services/app_services.py

### Phase 2: core_api 完全統合（4-6時間）
1. TagRegisterService を core_api.register_tag() ベースに変更
2. TagStatisticsService の全関数を core_api 統合
3. TagCleanerService の評価（core_api 不要なら現状維持）
4. 統合テスト追加（test_service_core_api_integration.py）

**主要変更**:
```python
# Before
def register_tag(self, request: TagRegisterRequest):
    repo = TagRepository(...)
    repo.create_or_update_tag(...)

# After
def register_tag(self, request: TagRegisterRequest):
    result = core_api.register_tag(request)
    return result
```

### Phase 3: 非同期化とライフサイクル管理（3-4時間）
1. WorkerService パターン導入（LoRAIro 参考）
2. TagSearchWorker 実装（非同期検索）
3. サービス初期化パターン統一（showEvent ベース遅延初期化）
4. MainWindow.closeEvent でリソース解放

**新規ファイル**:
- gui/services/worker_service.py（~150行）

**Widget 統一パターン**:
```python
def showEvent(self, event: QShowEvent):
    if self._service and not self._initialized:
        self.initialize_ui()
        self._initialized = True
    super().showEvent(event)
```

### Phase 4: テスト拡充（6-8時間）
1. Widget 単体テスト（pytest-qt）
   - test_tag_search_widget.py（10+ tests）
   - test_tag_register_widget.py（8+ tests）
   - test_tag_statistics_widget.py（6+ tests）
   - test_tag_cleaner_widget.py（4+ tests）
2. MainWindow 統合テスト
   - test_main_window_initialization.py（非同期DB初期化）
3. カバレッジ75%達成確認

## ファイル変更一覧

### 修正対象ファイル
| ファイル | Phase | 変更内容 | 行数変化 |
|---------|-------|---------|---------|
| gui/windows/main_window.py | 3 | closeEvent追加 | +20 |
| gui/widgets/tag_search.py | 1,3 | 型ヒント、非同期化 | +30 |
| gui/widgets/tag_register.py | 1,3 | 型ヒント、初期化統一 | +25 |
| gui/widgets/tag_statistics.py | 1,3 | 型ヒント、非同期化 | +35 |
| gui/widgets/tag_cleaner.py | 1 | 型ヒント追加 | +10 |
| services/app_services.py | 2,3 | core_api統合、close()追加 | +80 |

### 新規ファイル
| ファイル | Phase | 目的 | 行数 |
|---------|-------|------|------|
| gui/services/worker_service.py | 3 | 非同期タスク管理 | ~150 |
| tests/unit/gui/widgets/test_tag_search_widget.py | 4 | Widgetテスト | ~120 |
| tests/unit/gui/widgets/test_tag_register_widget.py | 4 | Widgetテスト | ~100 |
| tests/unit/gui/widgets/test_tag_statistics_widget.py | 4 | Widgetテスト | ~80 |
| tests/unit/gui/widgets/test_tag_cleaner_widget.py | 4 | Widgetテスト | ~50 |
| tests/integration/test_main_window_initialization.py | 4 | MainWindowテスト | ~80 |
| tests/integration/test_service_core_api_integration.py | 2 | core_api統合テスト | ~100 |

## 成功基準

1. ✅ 全 Widget が core_api 経由でデータ取得
2. ✅ pytest-qt ベースの Widget テスト 15+ 件
3. ✅ Ruff lint/format 100% 準拠
4. ✅ 大規模検索（1000+ 件）でも UI フリーズなし
5. ✅ カバレッジ 75% 以上達成

## 検証方法

### フェーズごと
```bash
# Phase 1: Lint チェック
uv run ruff check local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/

# Phase 2: 統合テスト
uv run pytest local_packages/genai-tag-db-tools/tests/integration/

# Phase 3: GUI手動テスト（非同期動作確認）
uv run python -m genai_tag_db_tools.main

# Phase 4: カバレッジ確認
uv run pytest local_packages/genai-tag-db-tools/tests/ \
    --cov=local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui \
    --cov-report=term
```

## リスク管理

### 高リスク項目
1. **core_api 統合時の動作確認**
   - 検証: pytest-qt での GUI 自動テスト（Phase 4 で実装）

2. **非同期化による UI バグ**
   - 対策: showEvent ベース遅延初期化
   - 検証: pytest-qt で Signal タイミングテスト

3. **テスト追加時の実装遅延**
   - 対策: タイムボックス設定（Widget 2時間まで）
   - 検証: 優先度付け（TagSearchWidget 優先）

## 次のアクション

### 実装開始コマンド
```bash
/implement
```

### 実装前確認
1. ブランチ確認: `refactor/db-tools-hf` または新規 `feature/gui-refactor-complete`
2. 既存テスト全 PASS: `uv run pytest local_packages/genai-tag-db-tools/tests/`
3. core_api.py の関数確認: `register_tag()`, `get_statistics()`
4. Ruff 環境確認: `uv run ruff --version`

## 実装スケジュール

| フェーズ | 所要時間 | 累積時間 |
|---------|---------|---------|
| Phase 1: コード品質改善 | 2-3h | 2-3h |
| Phase 2: core_api 完全統合 | 4-6h | 6-9h |
| Phase 3: 非同期化・ライフサイクル | 3-4h | 9-13h |
| Phase 4: テスト拡充 | 6-8h | 15-21h |

**総所要時間**: 15-21時間（2-3日）

## 参考実装
- Qt 非同期処理: QThreadPool + QRunnable パターン
- pytest-qt テスト: 既存の genai-tag-db-tools テストコード

### 関連メモリ
- `.serena/memories/genai_tag_db_tools_refactor_plan_2025_12_20.md`
- `.serena/memories/genai_tag_db_tools_refactor_progress_2025_12_20.md`
- `.serena/memories/genai_tag_db_tools_service_layer_core_api_integration_2025_12_23.md`

## 計画詳細

完全な実装計画は以下に保存されています：
`/home/vscode/.claude/plans/immutable-tumbling-quokka.md`

## 最新決定

- GUIサービスは core_api 経由のみとし、legacy 互換コードを削除して全面書き直す。
- TagRegisterService／TagStatisticsService は core_api での検索・登録・統計処理を別モジュールに実装。
- 非同期処理は QThreadPool + QRunnable（WorkerService）で統一し、進捗やキャンセルは省いて inished と error だけを利用。
- showEvent 初期化はサービスが揃っている前提で、UI 内で DB 初期化や重い処理を行わない。
- closeEvent はサービス close → DB close → super().closeEvent の順で処理し、例外をログに記録しつつ続行。
- エラーハンドリング規約：ValidationError/ValueError→warning + UI + signal、FileNotFoundError→warning + signal、それ以外→critical + signal + logger.exception。
- Ruff はコード全体と 	ests/ を含めて実行し、Phase 4 で全体 75% のカバレッジを目指す。
