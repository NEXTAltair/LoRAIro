# Legacy venv分離処理の完全クリーンアップ完了

## 実施日
2025年10月20日

## 背景
過去にWindows/Linux環境で`.venv_linux`/`.venv_windows`を分離していた時期の処理が、プロジェクト全体のドキュメント・設定・コマンド定義に残存していた。現在は`.venv`統一方針（devcontainer volume mount）に移行済みだが、古い参照が混在し開発者に混乱を与える可能性があった。

## 実施内容

### Phase 1: Claude Code設定ファイル
**修正ファイル**:
- `.claude/commands/plan.md` - テスト計画コマンド (3箇所修正)
- `.claude/commands/implement.md` - 実装・品質チェックコマンド (9箇所修正)
- `.claude/skills/lorairo-test-generator/SKILL.md` - pytest実行例 (6箇所修正)
- `.claude/skills/lorairo-qt-widget/SKILL.md` - UI生成コマンド (1箇所修正)
- `.claude/settings.local.json` - 自動承認ツールパターン (1箇所修正)

**変更内容**:
```bash
# 変更前
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest

# 変更後
uv run pytest
```

### Phase 2: プロジェクトドキュメント
**修正ファイル**:
- `CLAUDE.md` - 環境管理セクション (2箇所修正)
- `.serena/memories/architecture_structure.md` - 環境アーキテクチャ (3箇所修正)
- `.serena/memories/development_guidelines.md` - 環境分離ポリシー (1箇所修正)
- `.serena/memories/suggested_commands.md` - コマンド例 (1箇所修正)

**変更内容**:
- "Cross-Platform: Use `.venv_linux` for development/testing, `.venv_windows` for execution" → "Virtual Environment: The project uses `.venv` directory (managed by devcontainer volume mount)"
- 環境変数指定削除、uvのデフォルト動作に統一

### Phase 3: ローカルパッケージ
**genai-tag-db-tools**:
- `Makefile` (12箇所) - 全ターゲットから`UV_PROJECT_ENVIRONMENT`削除
- `scripts/setup.sh` - OS検出・環境変数設定ロジック完全削除
- `CLAUDE.md` - 環境管理説明を`.venv`統一版に更新

**image-annotator-lib**:
- `Makefile` (11箇所) - 全ターゲットから`UV_PROJECT_ENVIRONMENT`削除
- `scripts/setup.sh` - OS検出・環境変数設定ロジック完全削除

**統一後のsetup.sh**:
```bash
#!/bin/bash
echo "Setting up development environment..."
echo "Using default .venv directory"
uv sync --dev

if [ $? -eq 0 ]; then
    echo "✅ Environment setup complete!"
    echo "Virtual environment: .venv"
    echo "To run tests: uv run pytest"
fi
```

### Phase 4: その他の修正
- `scripts/generate_ui.py` - Usage例のコマンド修正 (1箇所)
- `.vscode/launch.json` - 既に`.venv`使用（確認のみ、修正不要）

## 残存する参照（意図的に保持）
以下のファイルは**履歴文書**として保持（新規開発者は参照しない）:
- `tasks/plans/` - 過去のプラン文書（参考記録）
- `tasks/implementations/` - 過去の実装記録（参考記録）
- `.serena/memories/venv_auto_activation_implementation.md` - 移行の経緯記録
- `.serena/memories/vscode_test_explorer_fix_20251020.md` - 問題解決の記録
- `local_packages/*/tasks/rfc/` - RFC文書（ローカルパッケージの設計記録）

## 設計原則

### uvのデフォルト動作活用
**原則**: `uv run`は自動的に`.venv`を検出・使用するため、`UV_PROJECT_ENVIRONMENT`指定は不要

**利点**:
- ✅ シンプルで保守しやすい
- ✅ uvの標準動作に準拠
- ✅ クロスプラットフォーム互換性
- ✅ devcontainer volume mount（.venv）と完全整合

### 環境変数削除の理由
1. **不要な複雑性**: uvが自動検出するため環境変数は冗長
2. **devcontainer環境**: 常にLinux、`.venv` volume mount済み
3. **Windowsローカル**: uvが自動的に`.venv`検出（Scripts/python.exe使用）

## 修正範囲の統計
- **合計修正ファイル数**: 15ファイル
- **削除された`UV_PROJECT_ENVIRONMENT`参照**: 約50箇所
- **削除された`.venv_linux`/`.venv_windows`参照**: 約40箇所
- **簡素化されたコード行数**: 約80行（setup.shの条件分岐削除等）

## 検証結果
```bash
# Legacy参照の検索（開発ファイルのみ）
grep -r "UV_PROJECT_ENVIRONMENT\|\.venv_linux\|\.venv_windows" \
  --include="*.md" --include="*.json" --include="*.sh" --include="Makefile" \
  --exclude-dir="tasks" \
  .

# 結果: 履歴文書・memory記録のみが残存（意図通り）
```

## 影響評価
✅ **既存ワークフローへの影響なし**: devcontainer環境は既に`.venv`使用中  
✅ **Windowsローカルへの影響なし**: uvが自動的に`.venv`検出  
✅ **ローカルパッケージ独立性維持**: 各パッケージで個別にテスト実行可能  
✅ **開発者体験向上**: 混乱を招く古い参照が完全除去

## 今後の運用方針

### 新規開発者向けガイド
- **最新ドキュメント**: `CLAUDE.md`、`.claude/commands/`、`.claude/skills/`を参照
- **環境セットアップ**: `./scripts/setup.sh` → 自動的に`.venv`使用
- **コマンド実行**: 全て`uv run <command>`で統一（環境変数不要）

### 維持管理
- 新規コマンド追加時は`UV_PROJECT_ENVIRONMENT`を使用しない
- ドキュメント更新時は`.venv`統一方針を踏襲
- 履歴文書（tasks/）は参考記録として保持（更新不要）

## 関連Memory
- [venv_auto_activation_implementation.md](venv_auto_activation_implementation.md) - `.venv`統一の初期実装
- [vscode_test_explorer_fix_20251020.md](vscode_test_explorer_fix_20251020.md) - 環境統一による問題解決
- [architecture_structure.md](architecture_structure.md) - 更新済みアーキテクチャ説明
- [development_guidelines.md](development_guidelines.md) - 更新済み開発ガイドライン

## 完了基準達成
✅ `.venv_linux`/`.venv_windows`文字列が開発ドキュメント・設定から完全除去  
✅ `UV_PROJECT_ENVIRONMENT`環境変数が不要なコマンドから削除  
✅ CLAUDE.md、commands、skillsで一貫した`.venv`使用を説明  
✅ local_packagesのMakefile/setup.shが簡素化  
✅ Memory記録に修正完了を記載（本ファイル）

## 参考資料
- **uv文書**: https://docs.astral.sh/uv/ - デフォルト`.venv`検出動作
- **devcontainer**: https://containers.dev/ - Volume mount仕様
- **プロジェクトメモリー**: 過去の設計判断と移行記録
