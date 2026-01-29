# LoRAIro × image-annotator-lib 統合計画

**作成日**: 2025-11-08
**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## 統合アプローチ: 段階的Protocol実装置き換え（採用）

### 選定理由
- 既存Protocol-based設計を最大活用
- テスタビリティ維持（Mock/Real切り替え容易）
- リスク最小（段階的実装）

### 不採用アプローチ
- 直接統合: Protocol-based設計が無駄に
- Facade + Adapter: 過度な抽象化層

## Phase 4 統合計画

### Phase 4-1: AnnotatorLibraryAdapter
- `src/lorairo/services/annotator_library_adapter.py`
- AnnotatorLibraryProtocol実装
- APIキー統合（lorairo.toml → image-annotator-lib）

### Phase 4-2: ModelSyncService
- MockAnnotatorLibrary → AnnotatorLibraryAdapter置き換え
- DB同期ロジック実装

### Phase 4-3: AnnotationService
- start_single_annotation()実装
- PHashAnnotationResults → LoRAIro形式変換
- エラーハンドリング・リトライ

### Phase 4-4: AnnotationWorker
- Worker進捗レポート統合
- キャンセル処理実装

### Phase 4-5: APIキー管理統合
- config/lorairo.toml → image-annotator-lib連携
- 環境変数対応
- APIキーマスキング

## テスト戦略
- Unit: Mock image-annotator-lib APIでテスト
- Integration: 実image-annotator-lib使用
- E2E: GUIからのアノテーション実行

## 制約条件
- image-annotator-libは変更不可
- Protocol-based設計を維持
- 既存Phase 2実装を維持
- 後方互換性必須
