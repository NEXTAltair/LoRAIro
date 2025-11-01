# image-annotator-lib 完成 マスタープラン

**作成日**: 2025-10-22
**目的**: ローカルパッケージ`image-annotator-lib`のPydanticAI統合完了とLoRAIroメインプロジェクトへの統合
**参照**: 本ドキュメントは全Phase共通の参照ドキュメント

---

## 📋 プロジェクト概要

### 実装目標
1. **PydanticAI統合の完全化**: 残プロバイダー（OpenRouter等）の統合完了
2. **テスト完全化**: 失敗テスト5件の修正、カバレッジ75%以上達成
3. **LoRAIro統合**: メインプロジェクトからの利用実装完了

### 作業優先順位
**環境整備 → テスト修正 → 統合**（ユーザー指定）

---

## 🔍 現状分析

### image-annotator-lib 現状
- **ブランチ**: `experiment/pydanticai-complete-adherence`
- **最新コミット**: 統一アノテーションシステムへの大規模リファクタリング完了
- **アーキテクチャ**:
  - 3層階層（BaseAnnotator → Framework-specific → Concrete models）
  - Provider-level PydanticAI統合（Anthropic, Google完了）
  - SimplifiedAgentFactory導入
- **開発履歴**:
  - 2025-06-30: PydanticAI統一エラー処理移行（89.4%成功率）
  - 2025-06-24: Google/Anthropic API PydanticAI統合完了

### テスト状況
- **総テスト数**: 1102テスト（LoRAIro + local_packages統合）
- **現在のカバレッジ**: 20.36%（目標: 75%以上）
- **失敗テスト**:
  - Google API Tests: 3件
  - Error Handling Integration Tests: 2件
- **テスト実行**: プロジェクトルートから`uv run pytest`

### 開発環境構成
- **Python**: 3.12（厳密要件 <3.13）
- **パッケージマネージャ**: uv 0.9.4
- **venv構成**: プロジェクトルート（`.venv`）統一管理、local_packagesと共有
- **依存関係**: `uv.lock`最新、変更不要
- **MCP統合**: serena（直接接続）+ cipher（Aggregator接続）
- **devcontainer**: volume mount（venv, extensions, bash_history）

### LoRAIro統合状況
- **統合ポイント**: `src/lorairo/annotations/`（現在未実装）
- **設定管理**: `config/lorairo.toml`からAPIキー読み込み
- **GUI統合**: MainWindow + WorkerService経由の非同期呼び出し
- **データフロー**: Direct Widget Communication パターン確立済み

---

## 💡 採用アプローチ

### アプローチA: 段階的統合（採用）
**理由**: 確実性と実用性のバランスが最適

**メリット**:
- 各段階で確実に動作確認できる
- 問題の切り分けが容易
- ロールバックポイントが明確

**実装方針**:
- Phase単位で計画→実装→検証のサイクル
- 各Phase完了時に動作確認
- 問題発生時は前Phaseに戻れる設計

---

## 📐 Phase構成

### Phase 1: 開発環境整備（1-2日）
**目的**: 安定した開発・テスト実行環境の確立

**主要タスク**:
1. 依存関係の検証と調整
2. テスト環境の統一
3. devcontainer設定の最適化

**成功基準**:
- `uv run pytest --collect-only`で全テスト収集可能
- image-annotator-libのimport成功
- 開発ツール（ruff, mypy）が正常動作

**詳細**: Phase 1完了後にserena memoryで詳細記録

---

### Phase 2: image-annotator-lib テスト修正（2-3日）
**目的**: テスト完全化とPydanticAI統合完了

**主要タスク**:
1. 失敗テスト5件の修正
2. テストカバレッジ向上（20% → 75%+）
3. PydanticAI統合の完全化（OpenRouter等）

**成功基準**:
- 全テストパス（0 failed）
- テストカバレッジ75%以上達成
- PydanticAI統合完了

**詳細**: Phase 1完了後にserena memoryで詳細計画作成

---

### Phase 3: LoRAIroメインプロジェクト統合（2-3日）
**目的**: メインプロジェクトからの実用的な利用実装

**主要タスク**:
1. 統合インターフェース実装（`src/lorairo/annotations/`）
2. GUI統合（MainWindow + WorkerService）
3. 統合テスト（E2E動作確認）

**成功基準**:
- LoRAIro GUIからimage-annotator-lib呼び出し成功
- 実画像でのアノテーション動作確認
- エラーハンドリング正常動作

**詳細**: Phase 2完了後にserena memoryで詳細計画作成

---

## 🧪 テスト戦略

### テスト階層
```
Unit Tests (単体テスト)
  ├─ image-annotator-lib内部: 既存テスト修正・拡充
  └─ LoRAIro統合部: 新規テスト追加

Integration Tests (統合テスト)
  ├─ Provider Manager動作確認
  ├─ LoRAIroサービス層連携確認
  └─ 複数プロバイダー統合動作

E2E Tests (End-to-End)
  ├─ GUI操作 → アノテーション実行
  └─ 実画像データでの動作確認
```

### テストマーカー統一
- `unit`: ユニットテスト（全体）
- `integration`: 統合テスト
- `webapi`: Web APIテスト
- `fast`: 高速実行テスト（外部依存なし、<30s）
- `standard`: 標準ユニットテスト（軽いモック、<3min）
- `real_api`: 実API検証テスト

---

## ⚠️ リスクと対策

### リスク1: テスト修正の複雑性
**影響**: Phase 2の遅延
**対策**:
- スキップマーカー一時利用
- 段階的修正（失敗テスト1件ずつ対応）
- モック設定の段階的見直し

### リスク2: 依存関係の不整合
**影響**: 環境構築失敗、予期せぬエラー
**対策**:
- `uv.lock`厳密管理
- 環境再構築手順確立
- 依存関係変更のドキュメント化

### リスク3: PydanticAI API変更
**影響**: 既存統合コードの動作不良
**対策**:
- バージョン固定（pyproject.toml）
- PydanticAI変更監視
- 後方互換性確認

### リスク4: 統合時の予期せぬ問題
**影響**: Phase 3の大幅遅延
**対策**:
- 小単位での統合
- 頻繁な動作確認
- ロールバックポイント明確化

---

## 📊 タイムライン

```
Week 1: Phase 1（環境整備） + Phase 2開始（テスト修正）
  Day 1-2: Phase 1実装・検証
  Day 3-5: Phase 2開始（失敗テスト修正）

Week 2: Phase 2完了（テスト修正） + Phase 3開始（統合）
  Day 6-7: Phase 2完了（カバレッジ向上）
  Day 8-10: Phase 3開始（統合実装）

Week 3: Phase 3完了（統合） + 最終確認
  Day 11-12: Phase 3完了（E2Eテスト）
  Day 13: 最終確認・ドキュメント整備
```

**総工数見積**: 5-8日（フルタイム換算）

---

## 🎯 成功の定義

### 技術的成功基準
- [ ] 全テストパス（0 failed, 1102 passed）
- [ ] テストカバレッジ75%以上達成
- [ ] PydanticAI統合完全化（全プロバイダー対応）
- [ ] LoRAIro GUIからの実用的なアノテーション実行成功

### 品質基準
- [ ] コードスタイル準拠（Ruff, mypy）
- [ ] ドキュメント整備（各Phase serena memory記録）
- [ ] エラーハンドリング完全実装
- [ ] パフォーマンス確認（大量画像処理）

### 運用基準
- [ ] 開発環境再構築手順確立
- [ ] CI/CD対応準備（GitHub Actions等）
- [ ] Memory-First開発による知識蓄積

---

## 📚 関連ドキュメント

### プロジェクト構成
- `CLAUDE.md`: LoRAIroプロジェクト開発ガイド
- `local_packages/image-annotator-lib/CLAUDE.md`: image-annotator-lib開発ガイド
- `local_packages/image-annotator-lib/PYDANTICAI_MIGRATION_CHANGES.md`: PydanticAI移行記録

### Serena Memory参照
- `current-project-status`: LoRAIroプロジェクト状況
- `tech_stack`: 技術スタック
- `development_guidelines`: 開発ガイドライン
- `image_annotator_lib_completion_master_plan`: 本マスタープラン
- Phase完了後に各Phase詳細記録を追加作成

---

## 🔄 実行フロー

1. **マスタープラン承認**（本memory）
2. **Phase 1詳細計画作成** → `/plan`コマンドでPhase 1のみ計画
3. **Phase 1実行** → `/implement`コマンドで実装
4. **Phase 1検証** → `/test`コマンドで動作確認
5. **Phase 2詳細計画作成** → Phase 1完了後にserena memoryで作成
6. （以下、Phase毎に繰り返し）

---

**次のアクション**: Phase 1詳細計画の作成（`/plan`コマンド実行）
