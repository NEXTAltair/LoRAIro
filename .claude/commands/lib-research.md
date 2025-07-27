# Library Research & Specification Analysis

ライブラリの仕様把握・調査・問題解決のための包括的な調査コマンド

## 使用方法
```
/lib-research $ARGUMENTS
```

**$ARGUMENTS**: ライブラリ名、調査テーマ、エラーメッセージなどを指定
- 例: `PySide6`、`SQLAlchemy ORM relationships`、`ImportError: No module named 'xyz'`

## 調査実行手順

### 1. 基本情報収集
- **インストール確認**: `UV_PROJECT_ENVIRONMENT=.venv_linux uv list | grep ライブラリ名`
- **site-packages調査**: `.venv_linux/lib/python3.12/site-packages/ライブラリ名/` 内のファイル構造確認
- **バージョン・メタデータ**: `dist-info/METADATA` ファイル読み込み
- **依存関係**: `dist-info/RECORD` で関連ファイル確認

### 2. ソースコード分析
- **主要モジュール**: `__init__.py`、主要クラス・関数の定義確認
- **設定ファイル**: 設定オプション、デフォルト値の把握
- **型情報**: `.pyi` ファイル（存在する場合）の型定義確認
- **実装パターン**: コードサンプル、使用例の抽出

### 3. 公式情報検索
- **Context7 ドキュメント検索**: ライブラリの最新ドキュメント取得 (`mcp__context7__resolve-library-id` → `mcp__context7__get-library-docs`)
- **公式リポジトリ**: GitHub/GitLab リポジトリ検索・README確認
- **公式ドキュメント**: 公式サイト、API reference、チュートリアル
- **リリースノート**: 最新バージョンの変更点、Breaking Changes
- **GitHub Issues**: 既知の問題、Feature Request、解決策

### 4. 実装・問題解決情報
- **使用例・サンプル**: 公式examples、コミュニティ実装例
- **ベストプラクティス**: 推奨パターン、アンチパターン
- **トラブルシューティング**: よくある問題、解決方法
- **互換性情報**: Python版、OS依存、他ライブラリとの相性

### 5. LoRAIroプロジェクト固有分析
- **現在の使用状況**: `src/lorairo/` 内での使用箇所検索
- **設定ファイル**: `config/lorairo.toml` での関連設定確認
- **テストケース**: `tests/` 内の関連テスト確認
- **統合パターン**: LoRAIroアーキテクチャとの整合性確認

## 出力形式

調査結果を以下の形式で整理:

```markdown
# ライブラリ名 調査結果 ({調査対象}_{YYYYMMDD_HHMMSS}.md)

## 基本情報
- バージョン: x.x.x
- インストール状況: ✅/❌
- 依存関係: [リスト]

## 仕様・API概要
- 主要機能:
- 重要なクラス/関数:
- 設定オプション:

## 実装例・使用パターン
- 基本的な使用方法:
- LoRAIroでの統合例:
- 注意点・制限事項:

## 問題解決情報
- よくある問題:
- 解決方法:
- 関連Issue:

## 参考リンク
- 公式ドキュメント:
- GitHub リポジトリ:
- その他参考情報:
```

## 注意事項

- **UV環境使用**: 必ず `UV_PROJECT_ENVIRONMENT=.venv_linux` を指定
- **ドキュメント優先**: まず `@docs/architecture.md` `@docs/technical.md` で既存の統合状況を確認
- **セキュリティ考慮**: ソースコード読み込み時は悪意のあるコードに注意
- **情報の正確性**: 公式情報を優先し、推測を避ける
- **LoRAIro特化**: プロジェクト固有の要件・制約を考慮した分析

このコマンドは外部ライブラリの深い理解とLoRAIroプロジェクトでの効果的な活用を支援します。