---
type: Guide
title: Documentation Maintenance
status: Accepted
timestamp: 2026-06-29
tags: [process]
---
# ドキュメント保守方針

LoRAIro における 3 層ドキュメント構造の維持と更新の方針を定める。

## 利用者向け公開ガイド

GitHub Pages で公開する利用者向けガイドは `site/src/content/docs/` に配置する。日本語(`ja`)を原本とし、英語(`en`)・繁体字(`zh-tw`)・簡体字(`zh-cn`)を AI 支援で同期する。

更新手順、翻訳元の原文ハッシュ記録、翻訳の不足や鮮度の検証方法は `site/README.md` を参照する。ドキュメントサイトは Starlight で生成し、GitHub Actions から公開する(Sphinx は使用しない)。以下の開発者向け設計資料と ADR は引き続きリポジトリ内で管理し、利用ガイドとの内容重複を避ける。

## 3 層ドキュメント構造

| 層 | 対象ファイル | 更新頻度 | 内容 |
|---|---|---|---|
| Layer 1 | `CLAUDE.md` | 四半期ごと・主要アーキテクチャ変更時 | AI エージェント向けの指針とワークフロー |
| Layer 2 | `docs/*.md` | 機能完成時・パターン変更時 | 詳細な技術仕様と設計資料 |
| Layer 3 | コード(docstring) | リアルタイム | 常に正確な実装詳細 |

## `docs/` ファイル一覧

| ファイル | 目的 |
|---|---|
| `docs/architecture.md` | システム設計原則 |
| `docs/services.md` | 全サービスカタログ(サービス件数は直書きせず、`services.md` の注記に従い都度確認する) |
| `docs/integrations.md` | 外部パッケージ統合パターン |
| `docs/testing.md` | テスト戦略とベストプラクティス |
| `docs/technical.md` | 実装仕様 |
| `docs/provider-batch-api.md` | Provider Batch API の利用条件と運用ガイド |
| `docs/decisions/README.md` | ADR インデックス |
| `docs/lessons-learned.md` | バグパターンと教訓 |
| `docs/development-workflow.md` | 開発プロセス(本ドキュメントの姉妹文書) |
| `docs/cli.md` | `lorairo-cli` コマンドリファレンス |
| `docs/cli-rating-preflight.md` | CLI での rating 事前確認手順 |
| `docs/product_requirement_docs.md` | プロダクト要求仕様書(PRD) |
| `docs/DEPRECATIONS.md` | 廃止機能一覧 |
| `docs/release-checklist.md` | リリース手順チェックリスト |
| `docs/plans/` | ネイティブ Plan Mode の計画共有ディレクトリ |
| `docs/superpowers/` | superpowers スキル(`writing-plans`、`brainstorming`)の計画・設計出力先。スキルの既定出力パスとして維持し、`docs/plans/` とは出所で使い分ける |
| `docs/specs/` | 機能仕様(`application`、`core`、`interfaces`) |
| `docs/design/` | デザインバンドル(DesignSync 同期対象) |
| `docs/migration/` | データ移行ガイド |
| `docs/skill-evaluations/` | スキル評価シナリオ |

## Frontmatter(OKF)

ドキュメントには OKF(Open Knowledge Format)の YAML frontmatter を付与する。frontmatter を SSoT とし、種別・ドメイン・依存技術を機械可読にすることで、3 リポジトリ横断の検索と参照を容易にする。規約の SSoT は **ADR 0082**(語彙・適用範囲・移行戦略)および **ADR 0069**(ADR バンドル)である。

- **必須キー**: `type`(`ADR`、`Guide`、`Reference`、`Contract`、`Plan`、`Investigation`、`Report` のいずれか)
- **任意キー**: `title`、`status`、`timestamp`(`YYYY-MM-DD`)、`tags`(抽象的な機能や責務のみ記載し、技術名は入れない)、`depends_on`(強く依存する技術・ライブラリ・外部仕様)
- **持たないキー**: `version`(鮮度は `timestamp` と Git 履歴で判断する)、`packages`(ファイルパスで判別できる)
- **適用対象**: `docs/**/*.md` および `local_packages/*/docs/**/*.md`(`docs/decisions/*.md` は ADR 0069 のルールに従う)
- **対象外**: `README.md`、`CHANGELOG.md`、`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`index.md`、`log.md`、自動生成物
- **移行方針**: 段階的(lazy)に適用する。中核ドキュメントには付与済みであり、その他は新規作成または実質的な更新時に付与する

検証は CI で強制せず、エージェント判断で起動する(ADR 0069・0039 と同じ方針である)。

```bash
make docs-okf    # 通常 docs を --skip-missing で検証 (未付与は pass、付与済みのみ検証)
make adr-okf     # ADR バンドルを全件検証
```

## 更新タイミング

### `CLAUDE.md`(Layer 1)
- 四半期レビューによる陳腐化セクションの削除
- 新しい設計パターンの導入など主要アーキテクチャの変更時
- 新コマンドや hook 追加などワークフローの更新時
- エントリーポイントや主要コンポーネントなどクリティカルパスの変更時

### `docs/*.md`(Layer 2)
- 新規サービスを追加したら `docs/services.md` を更新する
- 外部パッケージの API を変更したら `docs/integrations.md` を更新する
- Provider Batch API の利用条件や運用を変更したら `docs/provider-batch-api.md` を更新する
- 新しいテストパターンを採用したら `docs/testing.md` を更新する
- 重要な設計判断を行ったら `docs/decisions/` に ADR を追加する
- バグパターンや教訓を得たら `docs/lessons-learned.md` を更新する

### コードの docstring(Layer 3)
- 関数・メソッドの実装時
- クラスの定義時
- モジュールの新規作成時

## 更新チェックリスト

### 機能完成時
- [ ] 新規サービスを追加した場合は `docs/services.md` を更新した
- [ ] 外部統合を変更した場合は `docs/integrations.md` を更新した
- [ ] 新しいテストパターンを導入した場合は `docs/testing.md` を更新した
- [ ] 重要な設計判断がある場合は `docs/decisions/` に ADR を追加した

### 月次レビュー(依存レビューと同じ枠、毎月 1 日前後)
- [ ] `docs-freshness-audit` スキルの**軽監査**(Phase 1 の機械スキャンのみ)を実行し、死パス参照・死リンク・バナー残置・git 管理外残骸・消し忘れ計画を検出した

### 四半期レビュー
- [ ] `docs-freshness-audit` スキルの**深監査**(Phase 1〜3 フルセット)を実行し、並列エージェントによる実装照合と「更新・削除・ADR 移送」の処遇判断まで完了した
- [ ] `CLAUDE.md` の陳腐化したセクションを削除した
- [ ] `docs/*.md` の記述が実装と一致しているか確認した
- [ ] ファイルパスとサービス数を検証した

### 主要アーキテクチャ変更時
- [ ] 影響を受ける `docs/*.md` を先に更新した
- [ ] 変更に合わせて `CLAUDE.md` の参照を更新した
- [ ] 変更内容を記録した ADR を `docs/decisions/` へ追加した

## 手動検証コマンド

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

### 3 層構造を採用する理由
- 安定要素(設計原則)と変動要素(ファイルパスやサービス一覧)を分離できる
- `CLAUDE.md` の更新を四半期レビュー程度に抑えられる
- 新規の `docs/` ファイルを追加しやすい

### `CLAUDE.md` に `docs/` へのポインタのみを置く理由
- 記述の重複を排除し、ドキュメント間の乖離を防ぐためである
- `CLAUDE.md` を AI エージェントが素早く走査しやすい長さに維持できる
- 仕様変更時の修正箇所を 1 箇所へ集約できる

## 保守履歴

- **2026-07-05: `docs/specs/` 実装照合監査(第 3 弾)**
  - 並列監査で実装と突き合わせ、現行ドキュメントでカバー済みの古い仕様書 4 本(`overall_workflow.md`、`ai_annotation_core_spec.md`、`filesystem_management.md`、`gui_interface.md`。いずれも DEPRECATED バナー付き)を削除した
  - `specs/core/image_processing.md` を現行実装へ同期した(AutoCrop の補色差分法、確認事項 3 件の解消、`ImageProcessingService` の追記、#717 のパッケージ構成)
  - `specs/interfaces/configuration_window.md` を全面的に書き直した(2025-04 の旧 UI 記述から、現行のタブ構成・pure Python UI・OK 時一括保存へ刷新)
  - `specs/application/image_processing_service.md` は実装一致を監査で確認し、注記を追記して維持した
- **2026-07-05: `docs/` 棚卸し(第 2 弾)**
  - 陳腐化したドキュメントを削除した(DEPRECATED 宣言済みの `ai_annotation_application_spec.md`、二世代前の GUI 再設計分析 `gui_redesign_before_after_analysis.md`、2025-08 の `technical/pyside6-comprehensive-guide.md`、未参照のテンプレート仕様 4 本、Serena 時代の `investigations/windows-display-issue-analysis.md`)
  - 設計判断は現行 ADR と `lessons-learned.md` に記録済みのため、ADR へ移送する対象はなかった
- **2026-07-05: `docs/` 棚卸し**
  - 置き換え済みの旧テスト移行計画(`new_test_architecture.md`、`migration_roadmap.md`、`conftest_template.py`)と `archived_ui/` を削除した(git 履歴から参照可能)
  - PRD を現行製品の実態に合わせて全面的に書き直した
  - 本ファイルの `docs/` 一覧表を実態へ同期し、`superpowers/` の役割分担を明記した
- **2026-04-07: Serena Memory 廃止(Issue #64)**
  - `docs/decisions/` の ADR フレームワークを追加した
  - `docs/lessons-learned.md` を新規作成した
  - `docs/plans/` の計画共有ディレクトリを追加した
  - `CLAUDE.md` を 674 行から約 200 行へスリム化した
- **2026-01-01: 3 層ドキュメントアーキテクチャ実装**
  - 30 件以上のパス誤りと欠損サービス記述を修正した
  - `docs/services.md`、`docs/integrations.md`、`docs/testing.md` を新規作成した
