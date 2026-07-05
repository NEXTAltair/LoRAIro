---
type: Guide
title: Documentation Maintenance
status: Accepted
timestamp: 2026-06-29
tags: [process]
---
# Documentation Maintenance

LoRAIro の3層ドキュメント構造の維持方針。

## 3層アーキテクチャ

| 層 | ファイル | 更新頻度 | 内容 |
|----|---------|---------|------|
| Layer 1 | `CLAUDE.md` | 四半期 / 主要アーキテクチャ変更時 | AI エージェント指向 + ワークフロー |
| Layer 2 | `docs/*.md` | 機能完成時 / パターン変更時 | 詳細な技術仕様 |
| Layer 3 | コード | リアルタイム | 常に正確な実装詳細 |

## docs/ ファイル一覧

| ファイル | 目的 |
|---------|------|
| `docs/architecture.md` | システム設計原則 |
| `docs/services.md` | 全サービスカタログ (件数は本表に直書きせず services.md 側の注記に従い都度確認する) |
| `docs/integrations.md` | 外部パッケージ統合パターン |
| `docs/testing.md` | テスト戦略とベストプラクティス |
| `docs/technical.md` | 実装仕様 |
| `docs/provider-batch-api.md` | Provider Batch API 利用条件と運用ガイド |
| `docs/decisions/README.md` | ADR インデックス |
| `docs/lessons-learned.md` | バグパターン・教訓 |
| `docs/development-workflow.md` | 開発プロセス（このファイルの姉妹）|
| `docs/cli.md` | lorairo-cli コマンドリファレンス |
| `docs/cli-rating-preflight.md` | CLI rating 事前確認手順 |
| `docs/product_requirement_docs.md` | プロダクト要求 (PRD) |
| `docs/DEPRECATIONS.md` | 廃止機能一覧 |
| `docs/release-checklist.md` | リリース手順チェックリスト |
| `docs/plans/` | ネイティブ Plan Mode 計画の共有ディレクトリ |
| `docs/superpowers/` | superpowers skill (`writing-plans` / `brainstorming`) の計画・設計出力先。skill のデフォルト出力パスなので変更しない。`docs/plans/` とは出所で使い分ける |
| `docs/specs/` | 機能仕様 (application / core / interfaces) |
| `docs/design/` | デザインバンドル (DesignSync 同期対象) |
| `docs/migration/` | データ移行ガイド |
| `docs/skill-evaluations/` | skill 評価シナリオ |

## Frontmatter (OKF)

ドキュメントには OKF (Open Knowledge Format) の YAML frontmatter を付ける。frontmatter を
SSoT とし、種別・ドメイン・依存技術を機械可読にして 3 リポジトリ横断で検索・参照しやすくする。
**規約の SSoT は ADR 0082**（語彙・適用範囲・移行戦略）と ADR 0069（ADR バンドル）。

要点:

- **必須キー**: `type`（`ADR` / `Guide` / `Reference` / `Contract` / `Plan` / `Investigation` / `Report`）。
- **任意キー**: `title` / `status` / `timestamp`（`YYYY-MM-DD`）/ `tags`（抽象的な機能・責務、技術名は入れない）/
  `depends_on`（強依存する技術・ライブラリ・外部仕様）。
- **持たない**: `version`（鮮度は `timestamp` + Git）/ `packages`（パスで判別可）。
- **適用対象**: `docs/**/*.md`・`local_packages/*/docs/**/*.md`。`docs/decisions/*.md` は ADR 0069 ルール。
- **対象外**: `README.md` / `CHANGELOG.md` / `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `index.md` / `log.md` / 生成物。
- **移行**: 段階的（lazy）。中核 docs は付与済み、その他は新規作成・実質更新時に付与する。

検証（CI 強制せずエージェント判断で起動。ADR 0069/0039 と同じ思想）:

```bash
make docs-okf    # 通常 docs を --skip-missing で検証 (未付与は pass、付与済みのみ検証)
make adr-okf     # ADR バンドルを全件検証
```

## When to Update

**CLAUDE.md (Layer 1):**
- 四半期レビュー（陳腐化したセクションの削除）
- 主要アーキテクチャ変更（新設計パターン）
- ワークフロー更新（新コマンド、hook）
- Critical path 変更（エントリポイント、主要コンポーネント）

**docs/*.md (Layer 2):**
- 新サービス追加 → `docs/services.md` 更新
- 外部パッケージ API 変更 → `docs/integrations.md` 更新
- Provider Batch API の利用条件・運用変更 → `docs/provider-batch-api.md` 更新
- 新テストパターン採用 → `docs/testing.md` 更新
- 重要な設計判断 → `docs/decisions/` に ADR 追加
- バグパターン・教訓 → `docs/lessons-learned.md` 更新

**コード docstring (Layer 3):**
- 全関数/メソッド実装時
- 全クラス定義時
- 全モジュール作成時

## Update Checklist

**機能完成時:**
- [ ] 新サービス追加なら `docs/services.md` 更新
- [ ] 統合変更なら `docs/integrations.md` 更新
- [ ] 新テストパターンなら `docs/testing.md` 更新
- [ ] 重要な設計判断なら `docs/decisions/` に ADR 追加

**月次レビュー (dependency review と同枠、毎月1日近辺):**
- [ ] `docs-freshness-audit` skill の **軽監査** (Phase 1 機械スキャンのみ) を実行
      — 死パス参照 / 死リンク / バナー残置 / ignored 残骸 / 消し忘れ計画の検出

**四半期レビュー:**
- [ ] `docs-freshness-audit` skill の **深監査** (Phase 1+2+3 フルセット) を実行
      — 並列 agent での実装照合と「更新 / 削除 / ADR 移送」の処遇まで
- [ ] CLAUDE.md の陳腐化セクションを削除
- [ ] `docs/*.md` の正確性を確認
- [ ] ファイルパスとサービス数の検証

**主要アーキテクチャ変更時:**
- [ ] 影響を受ける `docs/*.md` を先に更新
- [ ] 変更に応じた CLAUDE.md 参照を更新
- [ ] 変更を記録した ADR を `docs/decisions/` に追加

## Manual Validation

```bash
# CLAUDE.md 内の全ファイルパスが存在することを確認
# サービス数が実際と一致することを確認
ls src/lorairo/services/*.py src/lorairo/gui/services/*.py | grep -v __init__ | wc -l

# ADR ファイルが存在することを確認
ls docs/decisions/

# docs/plans/ の最新計画確認
ls -la docs/plans/
```

## 設計原則

**なぜ3層構造か？**
- 安定要素（設計原則）と変動要素（ファイルパス、サービスリスト）を分離
- CLAUDE.md の更新が四半期レビューのみで済む
- 新 docs ファイル追加が容易

**なぜ docs/ へのポインタのみ CLAUDE.md に持つか？**
- 重複排除 = drift 防止
- CLAUDE.md が AI エージェント向けにスキャンしやすい状態を維持
- 変更は1箇所のみ

## Maintenance History

- 2026-01-01: 3層ドキュメントアーキテクチャ実装
  - 30+ のパスエラー・欠損サービスを修正
  - `docs/services.md`, `docs/integrations.md`, `docs/testing.md` を新規作成
- 2026-07-05: docs/specs/ 実装照合監査 (第3弾)
  - 並列監査で実装と突き合わせ、live docs がカバー済みの stale spec 4本を削除
    (`overall_workflow.md` / `ai_annotation_core_spec.md` / `filesystem_management.md` /
    `gui_interface.md` — いずれも DEPRECATED バナー付きだった)
  - `specs/core/image_processing.md` を現行実装に同期 (AutoCrop 補色差分法、
    確認事項3件の解消、ImageProcessingService 追記、#717 パッケージ構成)
  - `specs/interfaces/configuration_window.md` を全面書き直し (2025-04 の旧 UI 記述 →
    現行のタブ構成・pure Python UI・OK 時一括保存)
  - `specs/application/image_processing_service.md` は実装一致を監査確認、注記を追記して維持
- 2026-07-05: docs/ 棚卸し (第2弾)
  - 陳腐化ドキュメント削除: DEPRECATED 宣言済み `ai_annotation_application_spec.md`、
    二世代前の GUI 再設計分析 `gui_redesign_before_after_analysis.md`、
    2025-08 の `technical/pyside6-comprehensive-guide.md`、未参照テンプレ spec 4本、
    Serena 時代の `investigations/windows-display-issue-analysis.md`
  - ADR へ移送する価値のある内容はなし (設計判断は現行 ADR / lessons-learned で記録済み)
- 2026-07-05: docs/ 棚卸し
  - Superseded 済み旧テスト移行計画 (`new_test_architecture.md` / `migration_roadmap.md` /
    `conftest_template.py`) と `archived_ui/` を削除 (git 履歴で参照可)
  - PRD を現行製品の実態に合わせて全面書き直し
  - 本ファイルの docs/ 一覧表を実態に同期 (`superpowers/` の役割分担を明記)
- 2026-04-07: Serena Memory 廃止 (Issue #64)
  - `docs/decisions/` ADR フレームワーク追加
  - `docs/lessons-learned.md` 新規作成
  - `docs/plans/` 計画共有ディレクトリ追加
  - CLAUDE.md を674行→約200行にスリム化
