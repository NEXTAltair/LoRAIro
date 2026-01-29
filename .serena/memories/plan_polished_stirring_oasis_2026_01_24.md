# Plan: polished-stirring-oasis

**Created**: 2026-01-24 12:20:55
**Source**: plan_mode
**Original File**: polished-stirring-oasis.md
**Status**: planning

---

# Devcontainer 設定最適化計画

## 目的
冗長性の削減と可読性の向上による devcontainer 設定の最適化

## 現状分析

### Base Image
`mcr.microsoft.com/devcontainers/python:dev-3.13-bookworm` は以下を既に含む:
- buildpack-deps (build-essential, git, curl, wget, gnupg, procps)
- Python 3.13 + pip + setuptools
- vscode ユーザー（sudo設定済み）

### 発見された問題

| 問題 | 詳細 | 影響 |
|------|------|------|
| 重複インストール | build-essential, git, curl等がbase imageに既存 | ビルド時間増加 |
| Node.js二重定義 | Dockerfile L60-66 + features/node:1 | 競合リスク |
| git feature冗長 | buildpack-depsに既に含まれる | 不要な処理 |
| apt-get分散 | 6回の独立したRUNコマンド | レイヤー増加 |

---

## 実装計画

### Phase 1: Dockerfile 冗長パッケージ削除

**削除対象** (base imageに既存):
- L37-49の以下を削除:
  - `build-essential` - buildpack-deps提供
  - `git` - buildpack-deps:bookworm-scm提供
  - `curl` - buildpack-deps提供
  - `wget` - buildpack-deps提供
  - `bash` - Debian base提供
  - `ca-certificates` - Debian base提供
  - `gnupg` - buildpack-deps提供
  - `procps` - Debian base提供
  - `lsb-release` - Debian base提供

**保持対象**:
- `zsh` - oh-my-zshで使用

### Phase 2: Node.js インストール方法統一

**現状**:
- Dockerfile L60-66: nodesource手動インストール
- devcontainer.json features: node:1

**方針**: features/node:1 に統一
- Dockerfile の Node.js インストール削除 (L60-66)
- features/node:1 を維持（nvm管理で柔軟性高い）

**postCreateCommand.sh との互換性確認済み**:
- L8: `NVM_DIR="/usr/local/share/nvm"` → features/node:1 のデフォルトパス
- L10-11: nvm 読み込み + `nvm use 20` → features が提供
- L24: `npm i -g @anthropic-ai/claude-code @google/gemini-cli` → 正常動作

### Phase 3: git feature 削除

**理由**: buildpack-deps に git が含まれ、最新版不要
- devcontainer.json から `ghcr.io/devcontainers/features/git:1` 削除

### Phase 4: apt-get RUN コマンド統合

**Before** (6つの独立RUN):
```dockerfile
RUN apt-get update && apt-get install -y ... # 基本パッケージ
RUN apt-get update && apt-get install -y ... # Docker CLI
RUN apt-get update && apt-get install -y ... # OpenGL
RUN apt-get update && apt-get install -y ... # SQLite
RUN apt-get update && apt-get install -y ... # xdg-utils
...
```

**After** (2つの統合RUN):
```dockerfile
# 1. Docker CLI (独自リポジトリ追加が必要)
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# 2. 全パッケージ一括インストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    # GUI/Qt headless
    libgl1-mesa-glx libgl1-mesa-dri libegl1-mesa libegl1-mesa-dev \
    libglib2.0-0 libxrender1 libxtst6 libxi6 libxrandr2 libasound2 \
    libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 libxss1 \
    libgconf-2-4 libnss3 libxcursor1 libxkbcommon0 libgtk-3-0 \
    # Database & tools
    sqlite3 libsqlite3-dev git-lfs jq \
    # Docker CLI
    docker-ce-cli \
    # Utilities
    zsh xdg-utils rsync parallel netcat-openbsd \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
```

### Phase 5: GitHub CLI インストール統合

GitHub CLI も apt リポジトリ追加が必要なため、Docker CLI と同様に前処理:
```dockerfile
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null
```

その後の apt-get install に `gh` を追加

---

## 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| [.devcontainer/Dockerfile](.devcontainer/Dockerfile) | apt-get統合、冗長パッケージ削除、Node.js削除 |
| [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) | git feature削除 |

### 変更不要ファイル（調査済み）

| ファイル | 理由 |
|----------|------|
| [.devcontainer/postCreateCommand.sh](.devcontainer/postCreateCommand.sh) | 既に features/node:1 前提で設計済み（NVM_DIR="/usr/local/share/nvm"） |
| [Makefile](Makefile) | Node.js/npm への直接依存なし、uv コマンドのみ使用 |

---

## 期待される効果

| 指標 | Before | After |
|------|--------|-------|
| Dockerfileの行数 | 166行 | ~100行 |
| apt-get update回数 | 6回 | 1回 |
| レイヤー数 | 多数 | 削減 |
| ビルド時間 | 基準 | 短縮見込み |

---

## 検証手順

1. **ビルドテスト**
   ```bash
   docker build -t lorairo-test -f .devcontainer/Dockerfile .devcontainer/
   ```

2. **機能確認**
   ```bash
   # コンテナ内で確認
   node --version    # Node.js (features経由)
   git --version     # Git
   gh --version      # GitHub CLI
   docker --version  # Docker CLI
   sqlite3 --version # SQLite
   ```

3. **devcontainer再構築**
   - VS Code: "Dev Containers: Rebuild Container"
   - `uv sync --dev` が正常動作することを確認
   - `uv run pytest -m unit` でテスト実行

---

## リスクと対策

| リスク | 対策 |
|--------|------|
| features/node:1 と postCreateCommand.sh の互換性 | nvm use 20 が正常動作することを確認 |
| base imageのパッケージバージョン | 必要に応じて明示的バージョン指定 |
| ビルドキャッシュ無効化 | 初回のみ再ビルド時間増加、以降はキャッシュ有効 |
