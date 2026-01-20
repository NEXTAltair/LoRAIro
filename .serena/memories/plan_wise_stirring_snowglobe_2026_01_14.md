# Plan: MainWindow UI 再設計

**Created**: 2026-01-14 08:49:00
**Source**: plan_mode
**Original File**: wise-stirring-snowglobe.md
**Status**: approved
**Implementation Period**: 3 days

---

# MainWindow UI 再設計実装計画

**作成日**: 2026-01-14
**ステータス**: 実装準備完了
**目的**: トップレベルタブによる作業モード分離（ワークスペース ↔ バッチタグ）

## エグゼクティブサマリー

既存MainWindowを全面的に再設計し、トップレベルタブ構造（ワークスペース/バッチタグ）を導入します。**プログラム的UI再構成**アプローチを採用し、.uiファイル無変更で安全性を最大化します。

### 実装規模
- **実装期間**: 3日間
- **新規ファイル**: 3ファイル（サービス1 + テスト2）
- **修正ファイル**: 3ファイル（MainWindow、WidgetSetupService、docs）
- **コード追加**: 約500行
- **リスク**: 🟢 低（.uiファイル無変更、既存テスト維持）

### 主要な設計決定

1. **アプローチB（プログラム的UI再構成）を採用**
   - 理由: .uiファイル変更リスクを完全に回避
   - 根拠: FilterSearchPanel.setup_favorite_filters_ui()の成功事例

2. **TabReorganizationService新規作成**
   - 単一責任原則: タブ再構成ロジックを分離
   - テスタビリティ: ユニットテスト容易化

3. **5段階初期化へのPhase 2.5挿入**
   - 既存フローへの影響最小化
   - 既存テスト互換性維持

## 1. 現状分析

### 既存実装（src/lorairo/gui/window/main_window.py - 688行）

**構造**:
- 3ペインレイアウト: 左（検索）、中央（サムネイル）、右（プレビュー + 詳細タブ）
- 右パネル内タブ: 「画像詳細」「バッチタグ追加」

**強み**:
- 5段階初期化プロセス完全実装
- サービス層完全統合（29サービス）
- 75%+テストカバレッジ

**課題**:
- バッチタグ機能が右パネルの小さなタブに埋もれている
- 作業モード（閲覧 vs 一括編集）の視覚的分離が不明瞭

### モック提案（scripts/mock_main_window.py）

**構造**:
- トップレベルタブ: 「ワークスペース」「バッチタグ」
- ワークスペース: 既存3ペインレイアウト
- バッチタグ: 2カラム（ステージング画像グリッド + 操作パネル）

**利点**:
- 作業モードの明確な分離
- バッチタグ画面の全画面活用（画像視認性向上）
- UI構造のシンプル化

## 2. 実装アプローチ

### 推奨: アプローチB（プログラム的UI再構成）

**概要**: MainWindow.__init__内でプログラム的にQTabWidgetを追加し、既存ウィジェットを再配置。

**技術的根拠**:
- 既存パターンとの整合性: FilterSearchPanel.setup_favorite_filters_ui()実績
- Qt APIサポート: `layout.takeAt()` / `layout.addWidget()` による再親子化
- ロールバック容易性: git revert 1コマンドで即時復旧

**実装方針**:
1. MainWindow.uiは変更なし（安全性確保）
2. TabReorganizationService作成（タブ再構成ロジック分離）
3. Phase 2.5として既存初期化フローに挿入
4. 既存サービス接続をそのまま維持

### 他アプローチとの比較

| 観点 | A: Qt Designer完全再設計 | B: プログラム的再構成（推奨） | C: ハイブリッド |
|------|----------------------|----------------------|--------------|
| リスク | 🔴 高 | 🟢 低 | 🟡 中 |
| 複雑度 | 🔴 高 | 🟢 低 | 🟡 中 |
| 保守性 | 🟡 中 | 🟢 高 | 🟡 中 |
| 実装時間 | 3-5日 | 2-3日 | 2.5-3.5日 |

## 3. 実装ステップ（3日間）

### Day 1: 基盤 + ワークスペースタブ

**午前（4時間）: TabReorganizationService作成**
- [ ] `src/lorairo/gui/services/tab_reorganization_service.py` 新規作成（200行）
- [ ] `create_main_tab_widget()` - トップレベルQTabWidget生成
- [ ] `build_workspace_tab()` - 既存レイアウト再配置
- [ ] `extract_existing_widgets()` - ウィジェット抽出ユーティリティ

**午後（4時間）: MainWindow統合**
- [ ] `_create_main_tab_widget()` メソッド追加（Phase 2.5）
- [ ] 既存初期化フローへのPhase 2.5挿入
- [ ] 既存テスト実行（互換性確認）

**成果物**:
- TabReorganizationService完成
- ワークスペースタブ動作確認完了

### Day 2: バッチタグタブ

**午前（4時間）: レイアウト実装**
- [ ] `build_batch_tag_tab()` 実装
- [ ] 2カラムレイアウト作成（QHBoxLayout）
- [ ] ステージング画像グリッド実装（QGridLayout 3列）

**午後（4時間）: ウィジェット統合**
- [ ] BatchTagAddWidget配置
- [ ] AnnotationDataDisplayWidget追加（タグプレビュー）
- [ ] シグナル接続検証（tag_add_requested、staging_cleared）

**成果物**:
- バッチタグタブ完全実装
- MainWindow統合完了（688行 → 750行）

### Day 3: 状態管理 + テスト

**午前（4時間）: タブ切り替え + ユニットテスト**
- [ ] `_on_main_tab_changed()` 実装
- [ ] `_refresh_batch_tag_staging()` 実装
- [ ] `tests/unit/gui/services/test_tab_reorganization_service.py` 作成（8テスト、250行）

**午後（4時間）: 統合テスト + 検証**
- [ ] `tests/integration/test_main_window_tab_integration.py` 作成（5テスト、180行）
- [ ] 全テストスイート実行（75%+カバレッジ維持）
- [ ] `docs/services.md` 更新（TabReorganizationService追加）

**成果物**:
- 完全なテストスイート
- ドキュメント更新完了

## 4. 重要ファイル

### 新規作成

1. **src/lorairo/gui/services/tab_reorganization_service.py**
   - 責任: プログラム的タブ再構成ロジック
   - サイズ: 約200行
   - メソッド: `create_main_tab_widget()`, `build_workspace_tab()`, `build_batch_tag_tab()`

2. **tests/unit/gui/services/test_tab_reorganization_service.py**
   - テスト数: 8テスト
   - カバレッジ: タブ生成、レイアウト構造、ウィジェット配置

3. **tests/integration/test_main_window_tab_integration.py**
   - テスト数: 5テスト
   - カバレッジ: タブ切り替え、状態保持、サービス統合

### 修正

4. **src/lorairo/gui/window/main_window.py**
   - 変更内容: Phase 2.5挿入、タブ切り替えハンドラ追加
   - サイズ: 688行 → 750行（+62行）

5. **src/lorairo/gui/services/widget_setup_service.py**
   - 変更内容: `setup_batch_tag_tab_widgets()` メソッド追加
   - サイズ: 165行 → 200行（+35行）

6. **docs/services.md**
   - 変更内容: TabReorganizationService説明追加（GUIサービスセクション）
   - サイズ: +15行

## 5. 技術詳細

### Phase 2.5: トップレベルタブ作成

```python
def _create_main_tab_widget(self) -> None:
    """トップレベルタブウィジェット作成（Phase 2.5）"""
    try:
        self.tabWidgetMainMode = QTabWidget(self)
        TabReorganizationService.reorganize_main_window_layout(self)
        self.tabWidgetMainMode.currentChanged.connect(self._on_main_tab_changed)
        logger.info("Main tab widget created successfully")
    except Exception as e:
        logger.error(f"Failed to create main tab widget: {e}")
        self._handle_critical_initialization_failure("Main tab widget creation failed")
```

### タブ切り替えハンドラ

```python
def _on_main_tab_changed(self, index: int) -> None:
    """メインタブ切り替えハンドラ"""
    if index == 0:  # ワークスペース
        logger.info("Switched to Workspace tab")
    elif index == 1:  # バッチタグ
        logger.info("Switched to Batch Tag tab")
        self._refresh_batch_tag_staging()
```

### ステージングリフレッシュ

```python
def _refresh_batch_tag_staging(self) -> None:
    """バッチタグタブのステージングリスト更新"""
    if not hasattr(self, "dataset_state_manager"):
        return
    staged_images = self.dataset_state_manager.staged_images
    # ステージングサムネイルグリッド再描画
    logger.debug(f"Refreshed staging grid: {len(staged_images)} images")
```

## 6. リスク分析と対策

### リスク1: プログラム的レイアウトの可読性

**対策**:
- TabReorganizationServiceへの分離（単一責任原則）
- メソッド分割 + 詳細インラインコメント
- レイアウト構造図をdocstringに含める

### リスク2: タブ切り替えパフォーマンス

**対策**:
- サムネイル遅延ロード（表示領域外は読み込まない）
- QPixmapCache活用
- 最大表示数制限（500枚 → 200枚表示）

### リスク3: 既存テスト互換性

**対策**:
- Phase 2.5を既存Phaseの間に挿入
- `hasattr(main_window, "splitterMainWorkArea")` で条件分岐
- 段階的テスト実行

## 7. 検証項目

### 機能検証
- [ ] ワークスペースタブで画像検索・フィルタが動作
- [ ] ワークスペースタブで画像選択・プレビューが動作
- [ ] バッチタグタブでステージング画像が表示
- [ ] バッチタグタブでタグ追加が動作
- [ ] タブ切り替え時に状態が保持される

### テスト検証
- [ ] 全ユニットテスト合格
- [ ] 全統合テスト合格
- [ ] カバレッジ75%+維持
- [ ] 既存テストが破壊されていない

### コード品質検証
- [ ] Ruffフォーマット合格
- [ ] mypyタイプチェック合格
- [ ] docstring完備（Google style）

## 8. ロールバック計画

### ロールバック条件
- 既存テストの50%以上が失敗
- クリティカルなサービス統合破壊
- 実装時間が6日以上

### ロールバック手順
1. `git revert`（コード変更のみ）
2. 既存テスト全実行（正常復帰確認）
3. 代替アプローチの再検討

### ロールバック容易性
- ✅ .uiファイル無変更 → UI生成エラーのリスクなし
- ✅ コード変更のみ → git revert 1コマンドで復旧
- ✅ 既存テスト維持 → 正常復帰の即時確認可能

## 9. 成功基準

1. **機能要件**
   - トップレベルタブ（ワークスペース/バッチタグ）が動作
   - 既存サービス統合が維持される
   - タブ切り替えが滑らか（1秒以内）

2. **品質要件**
   - 全テスト合格
   - カバレッジ75%+維持
   - Ruff/mypy合格

3. **保守性要件**
   - TabReorganizationServiceの単体テスト完備
   - 詳細なドキュメント作成
   - ロールバック可能

## 10. 関連ドキュメント

- **現在の実装**: src/lorairo/gui/window/main_window.py
- **モック**: scripts/mock_main_window.py
- **Phase 4 & 5完了記録**: .serena/memories/mainwindow_ui_redesign_phase4_5_completion_2026_01_04.md
- **サービス一覧**: docs/services.md
- **アーキテクチャ**: docs/architecture.md
- **詳細設計**: .claude/plans/wise-stirring-snowglobe-agent-a520b8f.md
