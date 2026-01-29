# Cipher MCP Configuration Reference

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)
**目的**: Moltbot移行時の参照用

---

## Cipher概要
- HTTP MCP server at http://192.168.11.2:3000/http
- LoRAIroの複雑な分析・実装タスクを担当

## 旧MCP構成 (cipher.yml)

### 使用MCP Servers
1. **Serena**: コード読み取り、シンボル検索（/app内プロジェクト対象）
2. **context7**: ライブラリドキュメント検索（npx @upstash/context7-mcp）
3. **perplexity-ask**: Web検索（server-perplexity-ask）

### LLM設定
- Provider: OpenAI
- Model: gpt-5
- maxIterations: 50

### Embedding設定
- Type: openai
- Model: text-embedding-3-small

## Cipherの役割（旧方式）
- 複雑分析（10-30秒）: ライブラリ研究、設計パターン検索、実装実行
- Memory-first methodology: 既存知識を先に参照してから新規検索
- Serena（短期記憶）+ Cipher Memory（長期記憶）のデュアル戦略

## System Prompt要点
- 既存知識を先に参照（cipherMemory + Serena memories）
- 段階的作業: 発見→洞察記録→次ステップ提案
- 不確実性を明示、隠れた状態を仮定しない

## Moltbot移行時の考慮事項
- context7相当のライブラリ検索機能が必要
- 長期記憶の永続化方式を確認
- System Promptのmemory-first方針を引き継ぐかどうか
- Serenaとの連携パターンを再設計
