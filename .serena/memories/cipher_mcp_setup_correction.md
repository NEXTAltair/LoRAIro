# Cipher MCP Setup - 正しいコマンド構文 (2025-10-20修正)

## 誤った記録の修正

### 過去のメモリー記録（誤り）
`vscode_test_explorer_fix_20251020.md`に記録されていたコマンド:
```bash
claude mcp add cipher -s project -t sse -u http://192.168.11.2:5000/mcp/sse
```

**問題**: `-u`オプションは存在しない

### 正しいコマンド構文

#### SSEトランスポートの場合
```bash
claude mcp add cipher -s project -t sse http://192.168.11.2:5000/mcp/sse
```

または長い形式:
```bash
claude mcp add --scope project --transport sse cipher http://192.168.11.2:5000/mcp/sse
```

## claude mcp add の利用可能オプション

公式ヘルプ出力から確認済み:

- `-s, --scope <scope>`: local/user/project (デフォルト: local)
- `-t, --transport <transport>`: stdio/sse/http (デフォルト: stdio)
- `-e, --env <env...>`: 環境変数設定
- `-H, --header <header...>`: WebSocketヘッダー設定

**`-u`オプションは存在しない**

## 現在のdevcontainer.json設定

**108行目**:
```json
"mcpCipher": "claude mcp add cipher -t sse http://192.168.11.2:5000/mcp/sse"
```

**状態**:
- `-s project`オプション: ユーザーが削除（意図的）
- `-t sse`オプション: 存在（正しい）
- URL: `http://192.168.11.2:5000/mcp/sse` (正しい)

## プロジェクトスコープについて

`-s project`を使用しない理由:
- ユーザーの判断により削除
- local scope（デフォルト）で動作可能
- `.mcp.json`ではなくユーザー設定に保存される

## 正しい使用例

**公式ドキュメントのSSE例**:
```bash
claude mcp add --transport sse asana https://mcp.asana.com/sse
```

**Cipher適用例（現在の設定）**:
```bash
claude mcp add cipher -t sse http://192.168.11.2:5000/mcp/sse
```

## 検証日時
2025-10-20: `claude mcp add --help`出力で確認済み
