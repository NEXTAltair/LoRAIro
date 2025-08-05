# アーキテクチャ現代化実装計画書

## 📋 **プロジェクト概要**

**目的**: feature/cleanup-legacy ブランチのアーキテクチャリファクタリング変更を、制御された段階的ステップでmainブランチに統合する

**ブランチ戦略**: `feature/architecture-modernization` → 段階的統合 → `main`

## 🎯 **実装フェーズ**

### **フェーズ1: ModelRegistryServiceProtocol基盤構築**
**所要時間**: 1-2時間  
**優先度**: 高  
**リスク**: 低  

**統合対象の変更:**
- `src/lorairo/services/model_registry_protocol.py` 追加 (commit 3d62c2a)
- 純粋な抽象化レイヤー - 既存コード変更なし
- 含む内容: ModelInfo dataclass, Protocol定義, NullModelRegistry

**統合手順:**
1. プロトコルファイル作成をcherry-pick
2. 型チェック実行 (`uv run mypy src/`)
3. テスト実行で影響なしを確認 (`uv run pytest -m unit`)
4. コミット: "feat: add ModelRegistryServiceProtocol abstraction layer"

**成功基準:**
- ✅ 型チェック通過
- ✅ 既存テスト全通過
- ✅ 既存コードへの機能的変更なし

### **フェーズ2: ModelSelectionService現代化**
**所要時間**: 2-3時間  
**優先度**: 高  
**リスク**: 中  

**統合対象の変更:**
- `src/lorairo/gui/services/model_selection_service.py` 更新 (commit f5ad883)
- AnnotatorLibAdapter依存をModelRegistryServiceProtocolに置換
- 防御的プログラミングとエラーハンドリング追加

**統合手順:**
1. 現在のサービスのバックアップ作成
2. プロトコルベース変更適用
3. インポートと依存関係更新
4. サービス分離テスト (`uv run pytest tests/unit/gui/services/`)
5. コミット: "refactor: migrate ModelSelectionService to protocol-based architecture"

**成功基準:**
- ✅ 新アーキテクチャでサービステスト通過
- ✅ 後方互換性維持
- ✅ エラーハンドリング改善

### **フェーズ3: SearchFilterService拡張**
**所要時間**: 1-2時間  
**優先度**: 中  
**リスク**: 低  

**統合対象の変更:**
- `src/lorairo/gui/services/search_filter_service.py` 更新 (commit ac38f44)
- モデルフィルタリング機能追加
- 現代化されたModelSelectionServiceとの統合

**統合手順:**
1. 検索サービス拡張適用
2. フィルタリング機能テスト
3. 統合ポイント検証
4. コミット: "feat: enhance SearchFilterService with advanced model filtering"

**成功基準:**
- ✅ 拡張フィルタリング正常動作
- ✅ ModelSelectionServiceとの統合安定
- ✅ 大規模モデルリストでのパフォーマンス許容範囲

### **フェーズ4: ModelSelectionWidget統合**
**所要時間**: 2-3時間  
**優先度**: 高  
**リスク**: 高 (UI変更)  

**統合対象の変更:**
- `src/lorairo/gui/widgets/model_selection_widget.py` 更新 (commit 5263a8c)
- レガシーアダプターをサービス統合に置換
- 状態保持とエラーハンドリング追加

**統合手順:**
1. **統合前テスト**: 現在のウィジェット動作を文書化
2. ウィジェット現代化変更適用
3. **GUIテスト**: ウィジェット読み込み、選択、エラー状態テスト
4. **統合テスト**: 他UIコンポーネントとのテスト
5. **手動検証**: アプリケーション実行しモデル選択UI確認
6. コミット: "feat: integrate ModelSelectionWidget with modern service architecture"

**成功基準:**
- ✅ ウィジェットが正しくモデル読み込み
- ✅ 再読み込み時の選択状態保持
- ✅ エラー状態の適切な処理
- ✅ UI応答性維持

### **フェーズ5: ウィジェットシグナル処理現代化**
**所要時間**: 2-4時間  
**優先度**: 中  
**リスク**: 高 (コンポーネント間統合)  

**統合対象の変更:**
- ウィジェット統合とシグナル処理更新 (commit 2f44281)
- 複数ファイル: `annotation_coordinator.py`, `thumbnail.py`, `annotation_control_widget.py`
- シグナル契約とイベント処理の標準化

**統合手順:**
1. **シグナルマッピング分析**: 現在のシグナル流れを文書化
2. シグナル標準化変更適用
3. **コンポーネント統合テスト**: ウィジェット間相互作用テスト
4. **エンドツーエンドテスト**: 完全なアノテーションワークフローテスト
5. **回帰テスト**: 既存機能の完全性確保
6. コミット: "refactor: modernize widget integration and signal handling"

**成功基準:**
- ✅ 全ウィジェットシグナル正常動作
- ✅ コンポーネント間通信安定
- ✅ 既存ワークフローの回帰なし
- ✅ エラーハンドリングと安全性向上

## 🛡️ **リスク軽減戦略**

### **高リスクフェーズ (4 & 5)**
- **段階的コミット**: より小さな原子的変更
- **機能フラグ**: 必要時に旧動作への復帰可能性
- **包括的テスト**: 単体、統合、手動テスト
- **バックアップ戦略**: 主要変更前のブランチスナップショット

### **テストプロトコル**
各フェーズで必要:
1. **単体テスト**: `uv run pytest -m unit`
2. **統合テスト**: `uv run pytest -m integration`
3. **GUIテスト**: `uv run pytest -m gui` (ヘッドレス)
4. **手動テスト**: 重要ユーザーワークフロー
5. **パフォーマンスチェック**: 著しい劣化なし

### **ロールバック計画**
- 各フェーズで原子的コミット作成
- 個別フェーズの `git revert` 可能性
- 既知良好状態への `git reset`
- mainブランチ保護 (PR経由変更)

## 📊 **成功指標**

### **技術指標**
- ✅ 全テスト通過 (>1160テスト)
- ✅ 型チェッククリーン (`mypy`)
- ✅ リンティングクリーン (`ruff`)
- ✅ パフォーマンス回帰なし (5%以上遅くならない)
- ✅ メモリ使用量安定

### **機能指標**
- ✅ モデル選択ワークフロー完全
- ✅ アノテーション機能保持
- ✅ UI応答性維持
- ✅ エラーハンドリング改善
- ✅ コード保守性向上

## 📅 **タイムラインと依存関係**

**総推定時間**: 8-14時間  
**クリティカルパス**: フェーズ1→2→4→5  
**並行作業**: フェーズ3はフェーズ2と重複可能  

**依存関係:**
- フェーズ2はフェーズ1完了依存
- フェーズ3はフェーズ2完了依存  
- フェーズ4はフェーズ2&3完了依存
- フェーズ5はフェーズ4完了依存

## 🔄 **統合戦略**

### **ブランチ管理**
```
feature/architecture-modernization
├── phase-1-protocol-foundation
├── phase-2-service-modernization  
├── phase-3-search-enhancement
├── phase-4-widget-integration
└── phase-5-signal-modernization
```

### **マージ戦略**
- 各フェーズ: feature branch → architecture-modernization
- 最終統合: architecture-modernization → main (PR経由)
- main マージ前の包括的レビューとテスト

## 📋 **実装チェックリスト**

### **フェーズ開始前**
- [ ] 現在の動作を文書化
- [ ] テストベースライン確立
- [ ] バックアップブランチ作成

### **フェーズ実行中**
- [ ] 段階的変更適用
- [ ] 各ステップでテスト実行
- [ ] エラー時の即座停止・分析

### **フェーズ完了時**
- [ ] 全テストスイート実行
- [ ] 手動機能確認
- [ ] パフォーマンス測定
- [ ] コミット・文書化

この計画により、アーキテクチャ改善の系統的で低リスクな統合を、システム安定性と機能性を維持しながら実現します。