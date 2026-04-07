# Planning Memory Rules

計画策定時の過去知識活用ルール。Plan Mode・`/planning` コマンドの両方に適用。

## 必須: 計画策定前の知識確認

Plan Mode または `/planning` コマンドで計画を策定する際、コード調査の**前に**以下を確認すること:

### 1. 過去の設計判断確認（ADR）

```bash
ls docs/decisions/
```

- `docs/decisions/README.md` でインデックスを確認
- 関連する ADR を `Read docs/decisions/XXXX-*.md` で参照
- 類似の設計パターン・技術選定の根拠を確認

### 2. 教訓確認

```bash
# docs/lessons-learned.md を参照
```

- `docs/lessons-learned.md` でバグパターン・教訓を確認
- 特に同じドメイン（Architecture/Testing/Qt/DB/Integration）のセクションを重点的に確認

### 3. 最新の計画確認

```bash
ls -la docs/plans/
```

- `docs/plans/` の最新計画を確認（前回セッションの計画）
- 継続する計画がある場合は `Read docs/plans/plan_*.md` で参照

## 適用条件

- Plan Mode（ネイティブ）での計画策定時
- `/planning` コマンド実行時
- 新機能追加、アーキテクチャ変更、設計判断を伴うタスク

## スキップ可能な条件

- 単純なバグ修正（1-2ファイルの変更で設計判断不要）
- 同一セッションで既に確認済みの場合
- typo修正、コメント追加など設計判断を伴わない変更

## 計画完了後の知識保存

計画策定完了後、重要な設計判断は以下に保存すること:

**ADR（設計判断）:**
```
docs/decisions/XXXX-title.md に新しい ADR を追加
docs/decisions/README.md のインデックスを更新
```

**教訓（バグパターン）:**
```
docs/lessons-learned.md の該当ドメインセクションに追記
```

**OpenClaw LTM（長期・クロスプロジェクト）:**
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_write.py <<'JSON'
{
  "title": "LoRAIro [機能名] 設計判断",
  "summary": "設計アプローチの概要",
  "body": "# 設計詳細\n\n## 背景\n...\n\n## 判断\n...\n\n## 根拠\n...",
  "type": "decision",
  "importance": "High",
  "tags": ["関連タグ"],
  "source": "Container"
}
JSON
```

保存対象: アーキテクチャ決定、技術選定の根拠、パフォーマンス考慮事項、設計パターン選択
