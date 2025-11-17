# MainWindow初期化問題の診断記録

**作成日**: 2025-11-17
**発見契機**: アノテーション層統合後のGUI実動作テスト
**ステータス**: 診断完了、修正待ち
**優先度**: 高（GUI起動失敗）

## 1. 問題の発見

### エラーログ
```
2025-11-17 11:38:32.580 | ERROR | lorairo.gui.window.main_window:__init__ - MainWindow初期化失敗: 'MainWindow' object has no attribute 'selection_state_service'

2025-11-17 11:39:05.744 | ERROR | lorairo.gui.widgets.filter_search_panel:_on_search_requested - SearchFilterService not set
```

### 発見経緯
- 作業: アノテーション層統合完了後（コミット121a34b）
- 実行: Windows11ネイティブでのGUI起動テスト (`uv run lorairo`)
- 結果: MainWindow初期化エラー、検索機能無効

## 2. 根本原因の分析

### 発生源
- **原因ブランチ**: `feature/mainwindow-separation` (Phase 2.2〜2.9リファクタリング)
- **混入コミット**: `23e5d29` (Merge branch 'feature/mainwindow-separation' into feature/annotator-library-integration)
- **影響範囲**: `feature/annotator-library-integration`ブランチのみ
- **mainブランチへの影響**: なし（まだマージされていない）

### 初期化フローとエラー発生箇所
```
Phase 1 (L87): setupUi()
Phase 2 (L92): _initialize_services()
Phase 3 (L96): setup_custom_widgets()
  └─ L269: _setup_other_custom_widgets()
     └─ L278: _verify_state_management_connections() ← **エラー発生**
     └─ L285: SelectionStateService初期化（未到達）
Phase 3.5 (L100): _setup_search_filter_integration() ← **Phase 3失敗で未実行**
Phase 4 (L108): _connect_events() ← **未実行**

L112: except Exception でキャッチ → GUIは起動するが検索機能が使えない状態
```

## 3. 技術的詳細

### 問題1: SelectionStateService初期化順序エラー

**ファイル**: `src/lorairo/gui/window/main_window.py`

**問題箇所**:
- **L278**: `_verify_state_management_connections()` 呼び出し（SelectionStateService未初期化）
- **L285**: `SelectionStateService` 初期化

**エラー詳細**:
- L278時点では `self.selection_state_service` が存在しない
- L350-359の `_verify_state_management_connections()` が `SelectionStateService.verify_state_management_connections()` を呼び出す
- しかし、`SelectionStateService` に `verify_state_management_connections()` メソッドは**未実装**

**現在のコード（L350-359）**:
```python
def _verify_state_management_connections(self) -> None:
    """状態管理接続の検証（SelectionStateServiceに委譲）"""
    if self.selection_state_service:
        self.selection_state_service.verify_state_management_connections(
            thumbnail_selector=getattr(self, "thumbnail_selector", None),
            image_preview_widget=getattr(self, "image_preview_widget", None),
            selected_image_details_widget=getattr(self, "selected_image_details_widget", None),
        )
    else:
        logger.error("SelectionStateServiceが初期化されていません - 接続検証をスキップ")
```

### 問題2: SearchFilterService未注入

**ファイル**: `src/lorairo/gui/window/main_window.py`

**問題箇所**:
- **L100**: `_setup_search_filter_integration()` 呼び出し
- **Phase 3失敗により未実行**

**エラー詳細**:
- Phase 3 (L96) で例外発生 → L112でキャッチ
- Phase 3.5 (L100) が実行されない
- `FilterSearchPanel.search_filter_service` が None のまま
- 検索実行時に `SearchFilterService not set` エラー

**現在のコード（L697-699）**:
```python
except Exception as e:
    logger.error(f"SearchFilterService統合失敗: {e}", exc_info=True)
    logger.warning("検索機能は利用できませんが、その他の機能は正常に動作します")
```

**問題点**: 非致命的エラー扱い → 検索機能無効でもGUIが起動

## 4. 修正方針

### 修正1: SelectionStateService.verify_state_management_connections() の実装

**ファイル**: `src/lorairo/services/selection_state_service.py`

**修正内容**:
- クラス末尾に `verify_state_management_connections()` を追加し、必要ウィジェットの有無と接続状態をログ出力
- `thumbnail_selector`, `image_preview_widget`, `selected_image_details_widget` が未設定の場合は警告を出し、特に `thumbnail_selector` が無い場合は `DatasetStateManager` 連携が機能しない旨を通知
- `typing` から `Protocol` または `runtime_checkable` な簡易インターフェースを定義し、`Any` を避けて静的解析で検出できるようにする
- `DatasetStateManager` が `None` の場合は INFO ログを出して終了（それ以上検証しない）
- **導入意図**:
  - MainWindow初期化順序のバグを早期検出する軽量ガードをサービス側に持たせるため
  - UIコンポーネントとSelectionStateServiceの接続が欠けている状態をログで可視化し、silent failureを防ぐため
  - 将来、状態管理とUI接続を段階的にサービス層へ移譲する拡張ポイントとして機能させるため

### 修正2: SelectionStateService初期化順序の修正

**ファイル**: `src/lorairo/gui/window/main_window.py`
**箇所**: L273-293 (`_setup_other_custom_widgets()`)

**修正内容**:
- L285-292の `SelectionStateService` 初期化ブロックを L278 の**前に移動**
- 順序: SelectionStateService初期化 → `_verify_state_management_connections()` 呼び出し → その後で各Controllerを初期化
- `_verify_state_management_connections()` 呼び出しは維持し、サービスが正常に生成できなかった場合は `logger.error` を残して以降のController初期化で `None` を渡す

### 修正3: SearchFilterService注入失敗の致命的エラー化

**ファイル**: `src/lorairo/gui/window/main_window.py`
**箇所**: L674-699 (`_setup_search_filter_integration()`)

**修正内容**:
- 注入失敗時に `_handle_critical_initialization_failure()` を呼び出し、GUI起動を即座に中断
- 成功時には filterSearchPanel への注入ログと WorkerService 連携の可否ログを INFO で出す

**理由**: 検索機能はアプリケーションの必須機能であり、使えない状態での起動を許容しない（致命的失敗として扱う仕様に確定）

## 5. 修正対象ファイルと行数

| ファイル | 行番号 | 修正内容 |
|---------|--------|---------|
| `src/lorairo/services/selection_state_service.py` | クラス末尾 | `verify_state_management_connections()` 実装 |
| `src/lorairo/gui/window/main_window.py` | L273-293 | SelectionStateService初期化を検証呼び出しの前に移動 |
| `src/lorairo/gui/window/main_window.py` | L674-699 | SearchFilterService注入失敗を致命的エラー化 |

**修正ファイル数**: 1ファイル
**修正箇所**: 4箇所
**影響範囲**: 初期化フローのみ

## 6. 検証方法

修正後、以下を確認:

### 正常系
1. **Phase 3完了**: `✅ SelectionStateService初期化成功` ログ出力
2. **Phase 3.5完了**: `✅ SearchFilterService統合完了` ログ出力
3. **検索機能動作**: FilterSearchPanelで検索実行、エラーなし

### 異常系
4. **注入失敗時**: 致命的エラーダイアログ表示 + アプリケーション終了

## 7. 関連タスク・ブランチ

- **本タスク**: MainWindow初期化問題修正
- **別タスク**: アノテーション層統合（`.serena/memories/annotation_layer_architecture_reorganization_2025_11_15.md`）
- **修正ブランチ**: `feature/annotator-library-integration`（現在のブランチで修正）
- **Worktree不要**: 同一ブランチ内で修正（別の関心事だが、PRは分離しない）

## 8. リスク評価

- **リスク**: 低
- **理由**: 初期化順序の正常化と必須機能の明確化のみ
- **既存機能への影響**: なし
- **ユーザー影響**: 検索機能が使えない状態を許容しない方針への変更（むしろ品質向上）

## 9. 実装ステータス

- **診断**: 完了 ✅
- **修正**: 未着手
- **テスト**: 未実施
- **コミット**: 未実施

## 10. 次のアクション

1. ユーザーによる修正方針の確認
2. 修正実装
3. GUI起動テスト実行
4. コミット作成
