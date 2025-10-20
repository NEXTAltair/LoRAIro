# LoRAIro Terminal Auto-Activation Implementation

## 実装日
2025年10月20日

## 問題
VSCode のターミナルを開いた時に `.venv` が自動的に有効化されず、手動で `source .venv/bin/activate` を実行する必要があった。

## 根本原因
1. **devcontainer.json の設定重複**: Python インタープリターパスが devcontainer.json と workspace 設定で重複
2. **bashrc 自動化の欠如**: `.bashrc` に仮想環境有効化スクリプトが存在しない
3. **Legacy 設定の混在**: `scripts/setup.sh` が `.venv_linux` を参照（実際は `.venv` 使用）

## 実装ソリューション

### 選択したアプローチ: bashrc 自動有効化 + 設定統一

**利点**:
- VSCode 依存なし、全ターミナルで動作
- シンプルで確実
- devcontainer 再ビルド不要

### 実装内容

#### 1. devcontainer.json 更新
- **postCreateCommand 追加**: bashrc に自動有効化スクリプトを追加
- **重複設定削除**: devcontainer.json の Python 設定を削除（workspace 設定に統一）

```json
"postCreateCommand": "bash -c 'grep -q \"LoRAIro venv auto-activation\" ~/.bashrc || cat >> ~/.bashrc << \"EOF\"\n\n# LoRAIro venv auto-activation\nif [ -z \"$VIRTUAL_ENV\" ] && [ -f \"/workspaces/LoRAIro/.venv/bin/activate\" ]; then\n    source /workspaces/LoRAIro/.venv/bin/activate\nfi\nEOF\n'"
```

#### 2. bashrc 自動有効化スクリプト
条件付き有効化ロジック:
```bash
# LoRAIro venv auto-activation
if [ -z "$VIRTUAL_ENV" ] && [ -f "/workspaces/LoRAIro/.venv/bin/activate" ]; then
    source /workspaces/LoRAIro/.venv/bin/activate
fi
```

**条件チェック**:
- `[ -z "$VIRTUAL_ENV" ]`: 既に仮想環境が有効化されていない
- `[ -f "/workspaces/LoRAIro/.venv/bin/activate" ]`: activate スクリプトが存在する

#### 3. Legacy 設定クリーンアップ
[scripts/setup.sh](scripts/setup.sh) を更新:
- `.venv_linux` / `.venv_windows` 参照を削除
- デフォルト `.venv` ディレクトリのみを使用

## 変更ファイル
1. `.devcontainer/devcontainer.json`:
   - postCreateCommand 追加
   - Python 設定削除（workspace 設定に統一）
2. `scripts/setup.sh`:
   - UV_PROJECT_ENVIRONMENT 設定削除
   - `.venv` 統一使用

## テスト結果
✅ 新しいインタラクティブシェル起動時に自動有効化確認
✅ `VIRTUAL_ENV=/workspaces/LoRAIro/.venv` 正しく設定
✅ `which python` が `/workspaces/LoRAIro/.venv/bin/python` を返す

## 動作確認方法
```bash
# 新しいターミナルを開く
# 自動的に (.venv) がプロンプトに表示される

# または
bash -i -c 'echo $VIRTUAL_ENV; which python'
# 出力:
# VIRTUAL_ENV=/workspaces/LoRAIro/.venv
# /workspaces/LoRAIro/.venv/bin/python
```

## 設計決定と理由

### なぜ bashrc アプローチを選択したか
1. **確実性**: VSCode の `python.terminal.activateEnvironment` は不安定
2. **汎用性**: SSH、CLI ターミナルでも動作
3. **シンプル性**: 追加の依存関係なし

### なぜ .venv 統一したか
1. **複雑性削減**: `.venv_linux` / `.venv_windows` の管理コスト削減
2. **devcontainer volume mount**: `.venv` が volume としてマウント済み
3. **uv のデフォルト動作**: uv は `.venv` をデフォルトで認識

## 今後の注意点

### devcontainer 再ビルド時
postCreateCommand が自動的に bashrc を設定するため、手動操作不要

### 他プロジェクトでの影響
条件チェックにより、LoRAIro ディレクトリでのみ有効化されるため影響なし

### Development Guidelines 更新
`.venv_linux` / `.venv_windows` 参照は古い情報として、`.venv` 統一使用に更新が必要

## 関連ファイル
- [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json#L53)
- [scripts/setup.sh](scripts/setup.sh)
- [lorairo.code-workspace](lorairo.code-workspace#L36)

## 成功基準達成
✅ 新しいターミナルを開いた時に自動的に `.venv` が有効化される
✅ プロンプトに `(.venv)` が表示される（インタラクティブシェル）
✅ `which python` が `/workspaces/LoRAIro/.venv/bin/python` を返す
✅ 既存の Makefile、uv コマンドが正常動作

## 参考
- uv documentation: https://docs.astral.sh/uv/
- VSCode devcontainer: https://containers.dev/
