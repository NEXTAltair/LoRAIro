# DevContainer MCP Setup Timing Fix (2025-10-20)

## 問題
コンテナ起動時に`postStartCommand`でMCP設定コマンドが失敗していた（exit code 1）。

## 原因分析
- **Claude CLI インストール**: Dockerfile:126で`npm install -g @anthropic-ai/claude-code`によりビルド時にインストール済み
- **エラーの実際の原因**: postStartCommand実行タイミング（コンテナ起動直後）では、Claude Code環境が完全に起動しておらず`claude` CLIコマンドが利用不可能
- **タイムライン**: コンテナ起動(10:54:23) → claude CLI利用可能(22:50:59、約12時間後)

## 解決策
MCP設定コマンドを`postStartCommand`から`postAttachCommand`へ移動。

### 変更前(.devcontainer/devcontainer.json)
```json
"postStartCommand": {
    "hookPermissions": "chmod +x .claude/hooks/*.sh || true",
    "install": "make install-dev",
    "mcpSerena": "claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project /workspaces/LoRAIro",
    "mcpCipher": "claude mcp add cipher -t sse http://192.168.11.2:5000/mcp/sse"
}
```

### 変更後(.devcontainer/devcontainer.json)
```json
"postStartCommand": {
    "hookPermissions": "chmod +x .claude/hooks/*.sh || true",
    "install": "make install-dev"
},
"postAttachCommand": {
    "mcpSerena": "claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project /workspaces/LoRAIro",
    "mcpCipher": "claude mcp add cipher -t sse http://192.168.11.2:5000/mcp/sse"
}
```

## 設計判断の根拠

### DevContainer ライフサイクル
1. **postCreateCommand**: コンテナ初回作成時のみ実行
2. **postStartCommand**: コンテナ起動時に毎回実行（環境未完成の可能性）
3. **postAttachCommand**: IDE接続後に実行（Claude Code環境完全起動済み）

### 選択理由
- ✅ **IDE接続後実行**: postAttachCommandはClaude Code完全起動後に実行される
- ✅ **devcontainer仕様準拠**: ツール接続時の設定は本来postAttachCommandが想定用途
- ✅ **最小変更**: 既存コマンドの移動のみ（新規ファイル不要）
- ✅ **冪等性**: `claude mcp add`は既存設定を上書きするため複数回実行可能

### 検討した他のアプローチ
1. **リトライロジック**: postStartCommandでclaude CLI利用可能まで待機
   - ❌ 複雑なbashワンライナー（可読性低下）
   - ❌ 起動時間増加（最大60秒待機）
   
2. **専用スクリプト化**: .devcontainer/setup-mcp.sh作成
   - ❌ 新規ファイル追加（CLAUDE.md原則「ファイル作成最小化」に反する）
   - ❌ 起動時間増加

## 実装日
2025-10-20

## 検証方法
1. コンテナ再ビルド後、postAttachCommand実行確認
2. `claude mcp list`でserena/cipher接続確認
3. エラーログ確認（exit code 0期待値）

## 関連ファイル
- `.devcontainer/devcontainer.json`: MCP設定タイミング調整
- `.devcontainer/Dockerfile`: Claude CLI npm installは変更なし（Line 126）

## 技術参照
- DevContainer仕様: https://containers.dev/implementors/json_reference/
- Claude Code MCP: https://docs.claude.com/en/docs/claude-code/mcp
