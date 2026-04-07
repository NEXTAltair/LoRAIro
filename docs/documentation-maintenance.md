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
| `docs/services.md` | 全サービスカタログ (29 services) |
| `docs/integrations.md` | 外部パッケージ統合パターン |
| `docs/testing.md` | テスト戦略とベストプラクティス |
| `docs/technical.md` | 実装仕様 |
| `docs/decisions/README.md` | ADR インデックス |
| `docs/lessons-learned.md` | バグパターン・教訓 |
| `docs/development-workflow.md` | 開発プロセス（このファイルの姉妹）|
| `docs/plans/` | Plan Mode 計画の共有ディレクトリ |

## When to Update

**CLAUDE.md (Layer 1):**
- 四半期レビュー（陳腐化したセクションの削除）
- 主要アーキテクチャ変更（新設計パターン）
- ワークフロー更新（新コマンド、hook）
- Critical path 変更（エントリポイント、主要コンポーネント）

**docs/*.md (Layer 2):**
- 新サービス追加 → `docs/services.md` 更新
- 外部パッケージ API 変更 → `docs/integrations.md` 更新
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

**四半期レビュー:**
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
- 2026-04-07: Serena Memory 廃止 (Issue #64)
  - `docs/decisions/` ADR フレームワーク追加
  - `docs/lessons-learned.md` 新規作成
  - `docs/plans/` 計画共有ディレクトリ追加
  - CLAUDE.md を674行→約200行にスリム化
