# ADR 0019: Export Filter Required Design

- **日付**: 2026-04-22
- **ステータス**: Accepted

## Context

`lorairo-cli export create` コマンドの設計が、LoRAIro の本来目的と乖離している。

### 現状の課題

1. **本来目的**
   - LoRAIro の `export` 機能は **LoRA 学習用データセット作成** が目的
   - 学習データセットは「特定条件を満たす画像群」で構成される (例: 特定タグ、高評価、特定レーティング)
   - 「全件エクスポート」は学習用途として現実的に存在しない

2. **現状実装**
   - `src/lorairo/cli/commands/export.py:95` が `repository.get_images_by_filter()` を引数無しで呼び出す
   - 結果: フィルタ条件を明示しないと DB の全画像が取得される (例: 21,029 件)
   - Issue #166 で「指定プロジェクトの 9 件だけのはずが 21,029 件ハングアップ」と報告

3. **設計方針の歪み**
   - 当初は「プロジェクトフィルタを後から追加する」という方向で対応が検討された (Issue #166 原文の「対応方針(案)」)
   - しかしこれでは「フィルタ無し = 全件取得」という動作自体を正常ケースとして残してしまう
   - 大量データの誤エクスポートを構造的に防げない

## Decision

**`export create` コマンドはフィルタ条件を必須化する。フィルタ無しの呼び出しはエラーとして弾く。**

### 具体的変更

1. `export create` CLI 引数に以下のフィルタを追加:
   - `--project PROJECT`
   - `--tags "tag1,tag2"` / `--excluded-tags`
   - `--caption "..."`
   - `--manual-rating {PG|R|X|XXX}` / `--ai-rating {...}`
   - `--include-nsfw`
   - `--score-min FLOAT` / `--score-max FLOAT`

2. `src/lorairo/cli/commands/export.py:95` の `repository.get_images_by_filter()` 引数無し呼び出しを削除

3. バリデーション:
   - 上記フィルタが 1 つも指定されない場合 → `exit_code=2` + エラーメッセージ
   - エラーメッセージ例: `"エクスポートには最低1つのフィルタ条件が必要です。例: --project foo --tags cat"`

4. `ExportCriteria` (`src/lorairo/api/types.py`) に `has_any_filter()` メソッド追加:

```python
class ExportCriteria(BaseModel):
    # ... 既存フィールド ...
    
    def has_any_filter(self) -> bool:
        """フィルタ条件が1つ以上指定されているか検証。"""
```

5. GUI 側は既存の「選択状態からエクスポート」経路を維持 (`SelectionStateService.get_current_selected_images()` で最低 1 枚選択が保証されるため、実質的にフィルタ条件として機能)

## Rationale

### 検討した選択肢

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. フィルタ必須化 (エラー化) | フィルタ無し呼び出しを `exit_code=2` | **採用** |
| B. フィルタ無し時に警告 + 確認プロンプト | "全件エクスポートしますか? (y/N)" | 却下 |
| C. フィルタ無し時にドライラン強制 | 件数表示のみ、`--execute` 必須 | 却下 |
| D. 全件エクスポート許可 (現状維持 + バグ修正のみ) | 当初 Issue の方針 | 却下 |

### A を採用した理由

- **LoRA 学習目的との整合**: 学習用途で全件が必要な状況が想定できない。フィルタ必須は設計思想に沿う
- **構造的な誤操作防止**: 21,029 件の全件取得バグのような事故を、設計レベルで防げる
- **シンプルで一貫性**: ルールに例外が無く、ユーザーが覚えやすい
- **自動化スクリプトとの親和性**: 対話不要、失敗を即座に検知可能

### B (確認プロンプト) を却下した理由

- 非対話環境 (CI/CD、cron) で使えない
- 自動化スクリプトが `stdin` を詰まる
- LoRA 学習用の使用ケースで「本当に全件?」と聞く必要性が無い

### C (ドライラン強制) を却下した理由

- ユーザビリティ低下 (2 回コマンド実行が必要)
- `--execute` フラグが必須化するだけで、結局 B と同じ問題
- フィルタ必須化のほうがシンプルに目的達成できる

### D (現状維持) を却下した理由

- 全件取得バグの根本原因を残す (引数無し `get_images_by_filter()` の呼び出し可能性)
- ユーザーが意図せず 21,029 件をエクスポートする事故を再発可能
- LoRAIro の用途として不自然

## Consequences

### 良い点

- ◎ LoRA 学習目的に沿った一貫した動作
- ◎ 大量データ誤エクスポートの構造的防止
- ◎ CLI 引数から「エクスポート意図」が常に明示される (スクリプトの可読性向上)
- ◎ GUI 側は変更なし (選択状態が実質フィルタとして機能)

### トレードオフ

- △ 既存スクリプトが `export create --project foo --output /tmp/out` のような形で使われていた場合、破壊的変更で動かなくなる
- △ `--help` にフィルタオプションが増えて若干肥大化
- △ 初回利用者には「何でエラー?」という戸惑いを与える可能性

### 軽減策

- **エラーメッセージで移行ガイド表示**:
  ```
  Error: エクスポートには最低1つのフィルタ条件が必要です
  例: lorairo-cli export create --project foo --tags cat --output /tmp/out
  詳細: lorairo-cli export create --help
  ```
- **CHANGELOG で破壊的変更を明記**: migration section に「フィルタ条件必須化」を記載
- **`--help` の整理**: フィルタオプションをグループ化して視認性確保 (Typer の help グループ機能)

## Related

- Issue #166 (エピック): CLI export create リファクタリング
- Issue #173 [A]: このADRを実装するサブIssue (CLI フィルタ必須化)
- ADR 0006: Pagination Approach (全件取得の危険性との整合)
- ADR 0017: Project DB Normalization (プロジェクトフィルタの正規化実装)
