# Devcontainer設定最適化 (2026-01-24)

## 概要
冗長性削減と可読性向上のためのdevcontainer設定最適化を実施。

## 変更内容

### Dockerfile (166行 → 122行, 27%削減)

**削除したパッケージ** (base image `mcr.microsoft.com/devcontainers/python:dev-3.13-bookworm` に既存):
- build-essential, git, curl, wget, bash, ca-certificates, gnupg, procps, lsb-release

**削除した処理**:
- Node.js手動インストール (L60-66) → features/node:1 に統一

**統合した処理**:
- apt-get update: 6回 → 2回
- 外部リポジトリ設定 (Docker CLI, GitHub CLI) を1つのRUNに統合
- 全パッケージインストールを1つのRUNに統合

### devcontainer.json

**削除**:
- `ghcr.io/devcontainers/features/git:1` (buildpack-depsに既存)

**維持**:
- `ghcr.io/devcontainers/features/node:1` (nvm管理、postCreateCommand.sh互換)
- `ghcr.io/devcontainers/features/sshd:1`

## 影響を受けないファイル

| ファイル | 理由 |
|----------|------|
| postCreateCommand.sh | 既にfeatures/node:1前提 (NVM_DIR="/usr/local/share/nvm") |
| Makefile | Node.js/npm依存なし、uvコマンドのみ |

## Base Image情報

`mcr.microsoft.com/devcontainers/python:dev-3.13-bookworm` の継承チェーン:
```
python:3.13-bookworm
  → buildpack-deps:bookworm
    → buildpack-deps:bookworm-scm (git含む)
```

buildpack-depsに含まれるツール:
- build-essential (gcc, g++, make)
- git, curl, wget, gnupg, procps, lsb-release
- ca-certificates

## ボリューム名の固定化（セッション永続化対応）

### 問題
`${devcontainerId}` を使用したボリューム名は、devcontainerリビルド時に新しいIDが生成されるため、
以前のデータ（Claude Codeセッション、bash履歴など）が引き継がれない。

### 解決策
`${devcontainerId}` を削除し、固定のボリューム名を使用：

```json
"mounts": [
    "source=lorairo-bashhistory,target=/home/vscode/.bash_history,type=volume",
    "source=lorairo-vscode-extensions,target=/home/vscode/.vscode-server/extensions,type=volume",
    "source=lorairo-venv,target=/workspaces/LoRAIro/.venv,type=volume",
    "source=lorairo-claude-config,target=/home/vscode/.claude,type=volume"
]
```

### 変更理由
| ボリューム | 永続化理由 |
|-----------|-----------|
| lorairo-claude-config | Claude Codeセッション履歴、MCP設定、認証情報 |
| lorairo-bashhistory | シェル履歴 |
| lorairo-vscode-extensions | VS Code拡張機能キャッシュ（再インストール時間短縮） |
| lorairo-venv | Python仮想環境キャッシュ（uv sync時間短縮） |

### 古いボリュームからのデータ移行（ホストで実行）
```bash
# 古いボリュームを確認
docker volume ls | grep lorairo-claude-config

# データコピー（OLD_IDは実際のIDに置換）
docker run --rm \
  -v lorairo-claude-config-OLD_ID:/from \
  -v lorairo-claude-config:/to \
  alpine sh -c "cp -a /from/. /to/"

# 不要な古いボリュームの削除
docker volume rm lorairo-claude-config-OLD_ID
```

## 検証手順

```bash
# VS Code: "Dev Containers: Rebuild Container" 後
node --version    # Node.js (features経由)
git --version     # Git
gh --version      # GitHub CLI
docker --version  # Docker CLI
uv sync --dev     # Python依存関係
```
