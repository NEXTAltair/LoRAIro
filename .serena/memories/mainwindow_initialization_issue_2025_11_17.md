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

## 7. 関連タスク・ブランチ・Worktree戦略

### 実装済みタスク（同一ブランチ）
- ✅ **MainWindow初期化問題修正** (コミット a9b82a1)
- ✅ **Repository層アノテーションデータ修正** (コミット 0a82966)
- ✅ **Widget層データアクセス修正** (コミット 81f528f)
- ✅ **Repository層source判定修正** (コミット a1dfecb)

### 修正ブランチ
- **現在**: `feature/annotator-library-integration`
- **実装**: 同一ブランチ内で完了（4コミット）

### Worktree戦略の再評価

**当初判断（2025-11-17）**:
「Worktree不要: 同一ブランチ内で修正（別の関心事だが、PRは分離しない）」

**実績から得られた知見（2025-11-18）**:
初期化問題の修正中に**追加の不具合を3件発見**（Repository層データ構造、Widget層アクセスパターン、source判定ロジック）。
これらは初期化問題と**密接に関連**しており、同一PRで扱うことが適切だった。

**Worktree使用判断基準（確立）**:
| 条件 | Worktree使用 | 理由 |
|------|-------------|------|
| **関心事が完全に独立** | ✅ 推奨 | 並行開発可能、コンテキストスイッチ削減 |
| **関心事が部分的に重複** | ⚠️ 慎重判断 | データ競合・マージ競合リスク |
| **関心事が密接に関連** | ❌ 不要 | 同一ブランチで段階的実装が効率的 |

**本タスクの判断**: ❌ Worktree不要（関心事が密接に関連）

**別タスクでWorktreeが有効な例**:
- MainWindow分離リファクタリング（feature/mainwindow-separation）を継続しながら、
  annotator-library-integration での実装を並行する場合

## 8. リスク評価

- **リスク**: 低
- **理由**: 初期化順序の正常化と必須機能の明確化のみ
- **既存機能への影響**: なし
- **ユーザー影響**: 検索機能が使えない状態を許容しない方針への変更（むしろ品質向上）

## 9. 実装ステータス

- **診断**: 完了 ✅ (2025-11-17)
- **修正**: 完了 ✅ (2025-11-18)
  - MainWindow初期化順序修正 (a9b82a1)
  - Repository層データ修正 (0a82966, a1dfecb)
  - Widget層アクセスパターン修正 (81f528f)
- **テスト**: 完了 ✅
  - GUI起動・検索機能動作確認
  - 単体テスト 7/7成功
  - 統合テスト 5/5成功
- **コミット**: 完了 ✅ (4コミット)

**実装期間**: 2025-11-17 ~ 2025-11-18 (2日間)
**総変更ファイル**: 3ファイル
**総コミット数**: 4コミット

## 10. 気になる点・リスク

### リスク1: 自動テスト未整備
SearchFilterService 統合に失敗した場合に `_handle_critical_initialization_failure` が確実に呼ばれてアプリが終了することを確認する UI/統合テストがまだ無いので、今後の変更で挙動が変わっても気付きづらい状態です。少なくとも `filterSearchPanel` や `db_manager` をモックして失敗させるテストがあると安心です。

### リスク2: 状態検証ロジックの実質ノーチェック
`verify_state_management_connections()` は現状ウィジェットの存在可否をログに出すだけで、シグナル接続や StateManager 連携の整合性までは検証していません。将来「接続に失敗したら初期化を止める」まで踏み込む際には、ここを拡張する必要があります。

## 11. 推奨フォローアップ

### 11.1 テスト強化（優先度: 高）

#### 11.1.1 SearchFilterService致命エラー化のテスト
**ファイル**: `tests/integration/gui/test_mainwindow_initialization.py`（新規作成）

**テストケース**:
1. `test_searchfilterpanel_missing_triggers_critical_error`
   - filterSearchPanel が存在しない場合
   - `_handle_critical_initialization_failure` 呼び出し確認
2. `test_db_manager_missing_triggers_critical_error`
   - db_manager が存在しない場合
   - 致命的エラーダイアログ表示確認
3. `test_create_search_filter_service_exception_handling`
   - `_create_search_filter_service()` が例外を投げた場合
   - 適切なエラーハンドリング確認

**期待効果**: 初期化失敗時の確実な異常終了を保証

#### 11.1.2 verify_state_management_connections() の検証強化
**ファイル**: `src/lorairo/services/selection_state_service.py`

**拡張内容**:
1. **現状**: ログ出力のみ
2. **拡張案**:
   - シグナル接続の実在性検証（`hasattr`, `inspect.ismethod`）
   - DatasetStateManager との連携状態検証
   - 失敗時の適切なエラーハンドリング（`ValueError` raise）
3. **テスト追加**: `tests/unit/services/test_selection_state_service.py`

**期待効果**: Silent failure の完全排除

### 11.2 アーキテクチャ改善（優先度: 中）

#### 11.2.1 初期化フローの5段階パターン文書化
**ファイル**: `docs/gui_initialization_pattern.md`（新規作成）

**内容**:
- Phase 1-5 の詳細説明
- 各Phaseでの失敗ハンドリング戦略
- 致命的エラー vs 非致命的エラー判断基準
- コード例とベストプラクティス

**期待効果**: 新規Widget追加時の設計指針

#### 11.2.2 Dependency Injection パターンの統一
**現状課題**:
- SearchFilterService: メソッド注入（`_setup_search_filter_integration`）
- SelectionStateService: コンストラクタ生成（`_setup_other_custom_widgets`）
- 一貫性なし

**改善案**:
1. すべてのサービスをコンストラクタ注入に統一
2. `ServiceContainer` パターンの導入検討
3. テスタビリティの向上

**期待効果**: コードの予測可能性と保守性向上

### 11.3 モニタリング強化（優先度: 低）

#### 11.3.1 初期化時間の計測
**実装箇所**: `main_window.py` の各Phase

**内容**:
```python
@dataclass
class InitializationMetrics:
    phase1_time: float
    phase2_time: float
    phase3_time: float
    phase3_5_time: float
    phase4_time: float
    total_time: float
```

**期待効果**: パフォーマンス劣化の早期検出

### 11.4 関連メモリーの整理（優先度: 低）

**重複・古いメモリー**:
- `selected_image_details_widget_plan_2025_11_17.md`（古い計画）
- `selected_image_details_widget_plan_2025_11_18.md`（中間バージョン）
- `selected_image_details_widget_plan_2025_11_18_updated.md`（中間バージョン）

**統合済みメモリー**:
- `selected_image_details_widget_plan_2025_11_18_implementation_complete.md`（最終版）
- `metadata_display_fix_and_test_cleanup_2025_11_18.md`（包括記録）

**推奨アクション**: 中間バージョンの削除、最終版のみ保持

## 12. 実装完了

- **診断**: 完了 ✅
- **修正**: 完了 ✅
- **テスト**: GUI起動・検索機能動作確認完了 ✅
- **コミット**: a9b82a1 ✅

## 13. 実装中の発見事項

### 13.1 連鎖的バグの発見
初期化問題の修正中に、以下の関連バグを追加発見:

| 発見順 | 問題 | 原因 | 修正コミット |
|-------|------|------|-------------|
| 1 | SelectionStateService初期化順序エラー | 検証メソッドが初期化前に呼ばれる | a9b82a1 |
| 2 | Repository層データ構造不整合 | `_format_annotations_for_metadata()` のネスト構造 | 0a82966 |
| 3 | Widget層アクセスパターンミスマッチ | `metadata["annotations"]["tags"]` 期待 | 81f528f |
| 4 | Source表示ロジックバグ | `existing` フィールド未考慮 | a1dfecb |

**教訓**: 初期化問題はデータフローの上流から下流まで影響する可能性がある

### 13.2 テスト戦略の有効性確認
**実績**:
- 単体テスト: 7/7成功（Widget層の動作保証）
- 統合テスト: 5/5成功（E2Eシグナル接続検証）
- カバレッジ: 78%（修正ファイル）

**確認事項**:
- モックを最小限に抑えた統合テストが有効
- シグナル接続のE2E検証が必須
- 既存テスト資産（test_mainwindow_signal_connection.py）が活用できた

### 13.3 Worktree戦略の判断基準確立
**今回のケース**: Worktree不要（正しい判断）
**理由**: 初期化問題とデータ表示問題は密接に関連

**判断基準**:
- **関心事の独立性**: 完全独立 → Worktree推奨
- **データ競合リスク**: 高 → Worktree慎重判断
- **マージ頻度**: 高頻度 → 同一ブランチ推奨

## 14. まとめと次のステップ

### 実装完了内容
✅ MainWindow初期化順序問題の修正（4コミット）
✅ Repository/Widget層のデータ構造整合性確保
✅ 単体・統合テスト全12テスト成功
✅ GUI起動・検索機能の正常動作確認

### 残タスク
⚠️ SearchFilterService致命エラー化のテスト追加（優先度: 高）
⚠️ verify_state_management_connections() の検証強化（優先度: 高）
📝 初期化フローパターンの文書化（優先度: 中）

### 次のステップ
1. **PR作成**: `feature/annotator-library-integration` → `main`
   - タイトル: "fix: MainWindow初期化問題修正とアノテーション層統合"
   - 内容: 初期化順序修正 + Repository/Widget層修正
2. **テスト強化**: セクション11.1の実装（別PR）
3. **文書化**: 初期化パターンの標準化（別PR）
