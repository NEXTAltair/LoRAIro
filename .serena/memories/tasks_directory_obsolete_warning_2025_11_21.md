# tasks/ ディレクトリ廃止警告 - 古い指示の無効化

**日付**: 2025-11-21  
**状況**: tasks/ ディレクトリが残存し、古い `UV_PROJECT_ENVIRONMENT=.venv_linux` 指示を含む

## 問題

`tasks/` ディレクトリ（プロジェクトルート）に古いドキュメントが残存：

### 検出された古い指示

1. **tasks/implementations/implement_20250714_054000.md**:
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff check`
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run mypy`
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff format`

2. **tasks/plans/plan_20250717_044752.md**:
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit`
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration`
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui`

3. **tasks/plans/plan_image_annotator_lib_api_compatibility_fix_20250726.md**:
   - `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest`（複数箇所）

## 現在の正しい構成（2025-10-20 確立）

### 仮想環境

- **唯一の環境**: `/workspaces/LoRAIro/.venv`
- **廃止された環境**: `.venv_linux`、`.venv_windows`、`UV_PROJECT_ENVIRONMENT` 変数

### 正しいコマンド実行

```bash
# ✅ 正しい
cd /workspaces/LoRAIro
uv run pytest tests/

# ❌ 間違い（古い指示）
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/
```

### uv の自動認識

`uv run` は以下の順序で仮想環境を自動検出：
1. `.venv` ディレクトリ（プロジェクトルート）
2. `VIRTUAL_ENV` 環境変数
3. `pyproject.toml` の設定

**結論**: `UV_PROJECT_ENVIRONMENT` 設定は不要かつ非推奨。

## 対応方法

### tasks/ ディレクトリの扱い

**重要**: tasks/ ディレクトリ内のドキュメントは **参照禁止**

理由:
1. **情報の陳腐化**: 2025年7-8月の古い情報
2. **廃止された構成**: `.venv_linux` 使用前提
3. **MCP Memory への移行完了**: すべての最新情報は MCP memory に記録

### 参照すべきドキュメント

**✅ 信頼できる情報源**:
1. **CLAUDE.md**: プロジェクト指示（最新）
2. **MCP Serena memories**: プロジェクト記録
3. **venv_auto_activation_implementation memory**: 仮想環境構成（2025-10-20）

**❌ 参照禁止**:
- `tasks/` ディレクトリ内の全ファイル

## 関連メモリー

- `venv_auto_activation_implementation`: 仮想環境統一化（2025-10-20）
- `tasks_directory_removal_2025_11_06`: tasks/ 廃止記録（local_packages 配下）

## 教訓

**古いドキュメントの影響**:
- 計画書作成時に古い `UV_PROJECT_ENVIRONMENT` 指示を誤って参照
- 現在の構成（`.venv` 統一）と矛盾

**再発防止**:
- tasks/ ディレクトリは archive として保持
- 新規作業時は **MCP memory のみ参照**
- CLAUDE.md に tasks/ 参照禁止を明記（必要に応じて）
