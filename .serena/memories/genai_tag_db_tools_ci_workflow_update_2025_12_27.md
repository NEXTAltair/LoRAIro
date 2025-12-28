# genai-tag-db-tools CI Workflow Update (2025-12-27)

## 変更概要

リファクタリング後のプロジェクト構造に合わせて GitHub Actions CI ワークフローを更新。

## 主な変更点

### 1. Python対応バージョン拡張
- **pyproject.toml**: `requires-python = ">=3.10,<3.14"`
- **CI matrix**: Python 3.10, 3.11, 3.12, 3.13 で継続テスト
- 理由: ユーザー環境の多様性に対応

### 2. 不要なジョブ削除
- **削除**: `docs` ジョブ（Sphinx設定が存在しないため）
- **削除**: GitHub Pages デプロイ
- 理由: 現在docs/ディレクトリが存在せず、ドキュメント生成の設定がない

### 3. HuggingFace オフラインモード対応
- **追加環境変数**: `HF_HUB_OFFLINE=1`
- **pytest引数**: `-m "not slow"`（遅いテストをスキップ）
- 理由: CI環境でHFダウンロードを回避し、テスト高速化

### 4. CI設定最適化
- **`--all-extras` 削除**: プロジェクトにextra dependenciesなし
- **`--unsafe-fixes` 削除**: ruff checkから削除（安全性優先）
- **Codecov token追加**: `${{ secrets.CODECOV_TOKEN }}`（推奨設定）

### 5. 権限スコープ縮小
```yaml
permissions:
  contents: read  # 最小権限（write/pages不要）
```

## 実行ステップ

### Lint & Format
```bash
uv run ruff check src/genai_tag_db_tools
uv run ruff format --check src/genai_tag_db_tools
```

### Type Check
```bash
uv run mypy src/genai_tag_db_tools
```

### Test
```bash
QT_QPA_PLATFORM=offscreen HF_HUB_OFFLINE=1 \
  uv run pytest --cov=src/genai_tag_db_tools --cov-report=xml -m "not slow"
```

## テスト構成

- **総テスト数**: 210個
- **構造**: 
  - `tests/unit/`: 基本ロジックテスト
  - `tests/gui/unit/`: GUIコンポーネント単体テスト
  - `tests/gui/integration/`: GUI統合テスト

## 確認済み項目

✅ Ruff lint: All checks passed  
✅ Ruff format: 2 files reformatted (cli.py, core_api.py)  
✅ Test collection: 210 tests collected  
✅ Python version support: 3.10-3.13  

## 残タスク

- [ ] Codecov シークレット設定（リポジトリ側）
- [ ] 初回CI実行での動作確認
- [ ] slow markerの適切な適用確認

## ファイル変更

1. `pyproject.toml`: Python version constraint緩和
2. `.github/workflows/python-package.yml`: CI設定最適化
3. `src/genai_tag_db_tools/cli.py`: Ruff format適用
4. `src/genai_tag_db_tools/core_api.py`: Ruff format適用
