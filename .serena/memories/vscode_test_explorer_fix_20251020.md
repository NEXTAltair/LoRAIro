# VSCode Test Explorer修正セッション (2025-10-20)

## 問題概要
VSCode Test Explorerでpytestテスト検出が失敗する問題。
- "Falling back to tree search" エラー多発
- `TypeError: Cannot convert undefined or null to object` 発生
- 17個のテスト収集エラー（ローカルパッケージのテストを除く6個がメインプロジェクト）

## 根本原因
1. **coverageパッケージの破損**: `.venv_linux/lib/python3.12/site-packages/coverage-7.10.6.dist-info` の `RECORD` ファイル欠損
2. **環境分離の問題**: `.venv_linux` がホストとコンテナでマウント共有され、Windows/Linux間でパッケージ破損
3. **VSCode Test Explorerの直接実行**: `.venv_linux/bin/python` を直接使用するため、`uv run` の自動修復が効かない

## 解決策
`.venv` をコンテナ内専用Dockerボリュームに分離し、Windowsネイティブと完全分離。

### 実施済み変更

#### 1. `.devcontainer/devcontainer.json`
- `python.defaultInterpreterPath`: `.venv_linux/bin/python` → `.venv/bin/python`
- `remoteEnv`: `UV_PROJECT_ENVIRONMENT=.venv_linux` を削除
- `postStartCommand`: `.venv_linux` 参照を `.venv` に変更
- `mounts`: 新規追加 `"source=lorairo-venv-${devcontainerId},target=/workspaces/LoRAIro/.venv,type=volume"`

#### 2. `lorairo.code-workspace`
- `python.defaultInterpreterPath`: `${env:UV_PROJECT_ENVIRONMENT}/bin/python` → `.venv/bin/python`
- `python.testing.pytestArgs`: `--ignore=.venv_windows` を削除

### 次のステップ（コンテナリビルド後）
1. **動作確認**:
   ```bash
   ls -la .venv
   which python
   python --version
   uv run pytest --version
   ```

2. **`.venv_linux` 参照の一括修正**:
   - `Makefile`
   - `scripts/` 配下のスクリプト
   - `.claude/hooks/` のHookスクリプト
   - CLAUDE.md、README.md等のドキュメント
   - `.vscode/settings.json` (あれば)

## 環境設計
- **Windowsネイティブ**: `.venv/` (ホストのワークスペース内)
- **Devコンテナ**: `.venv/` (Dockerボリューム `lorairo-venv-${devcontainerId}`)
- **分離**: 両者は完全に独立、マウント共有なし

## 検証項目
- [ ] `.venv` が正しく作成される
- [ ] VSCode Test Explorerがテストを検出
- [ ] pytest直接実行が成功
- [ ] coverage動作確認
- [ ] Python拡張機能が正しいインタープリターを認識

---

## 追加修正: postCreateCommandエラー対応 (2025-10-20 後半)

### 発生した問題
コンテナリビルド時に以下のエラーが発生:
```
postCreateCommand from devcontainer.json failed with exit code 127
OCI runtime exec failed: exec failed: unable to start container process:
exec: "bash -lc 'set -euo pipefail; cd /workspaces/LoRAIro; make install-dev'":
stat bash -lc 'set -euo pipefail; cd /workspaces/LoRAIro; make install-dev':
no such file or directory: unknown
```

### 根本原因
1. **devcontainer.json**: `postCreateCommand`が配列形式で記述されていたが、各要素が**独立したコマンド名として扱われる**問題
   - `"bash -lc 'set -euo pipefail; cd /workspaces/LoRAIro; make install-dev'"` 全体が単一の実行可能ファイル名として解釈される
   - 正しくは配列の各要素を個別の引数として分割するか、単一の文字列にする必要がある

2. **Dockerfile**: 130行目のRUN構文エラー
   - 前のRUNブロックが閉じておらず、次のRUNと連結されていた

### 実施した修正

#### 1. `.devcontainer/devcontainer.json` (L104)
**修正前（配列形式 - エラー）**:
```json
"postCreateCommand": [
    "bash -lc 'set -euo pipefail; cd /workspaces/LoRAIro; make install-dev'",
    "bash -lc \"claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)\"",
    "bash -lc \"claude mcp add cipher -s project -t sse -u http://192.168.11.2:5000/mcp/sse\""
]
```

**修正後（単一文字列形式 - 正常）**:
```json
"postCreateCommand": "bash -c 'set -euo pipefail && cd /workspaces/LoRAIro && make install-dev && claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd) && claude mcp add cipher -s project -t sse -u http://192.168.11.2:5000/mcp/sse'"
```

**変更点**:
- 配列 → 単一文字列に変更
- `bash -lc` → `bash -c` (ログインシェル不要)
- セミコロン(`;`) → `&&` (エラー時に即停止)

#### 2. `.devcontainer/Dockerfile` (L130-136)
**修正前（構文エラー）**:
```dockerfile
RUN sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended \
    && echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc \

    # Set bash history persistence
    RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc
```

**修正後（正しい構文）**:
```dockerfile
RUN sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended \
    && echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc

# Set bash history persistence
RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc
```

**変更点**:
- 131行目の末尾のバックスラッシュ削除
- 133行目のRUNを独立したコマンドとして分離

### 期待される効果
1. **postCreateCommandが正常実行される**:
   - `make install-dev` → `.venv` (Dockerボリューム)に依存関係がインストールされる
   - Serena MCP設定が自動適用される
   - Cipher MCP設定が自動適用される

2. **Dockerイメージが正常にビルドされる**:
   - RUN構文エラーが解消され、ビルドプロセスが完了する
   - zsh/bash設定が正しく適用される

3. **コンテナ起動後の状態**:
   - `.venv/` (Dockerボリューム)が完全にセットアップされた状態で利用可能
   - MCP接続が即座に利用可能
   - VSCode Test Explorerが正しいPython環境を参照

### 検証手順（リビルド後）
```bash
# 1. 環境確認
ls -la .venv
which python
python --version

# 2. 依存関係確認
uv run pytest --version
uv run mypy --version

# 3. MCP接続確認
claude mcp list

# 4. テスト実行
uv run pytest tests/ -v
```
