# ADR 0018: Project Storage Unification (lorairo_data/ 配下統一)

- **日付**: 2026-04-22
- **ステータス**: Accepted

## Context

LoRAIro の GUI と CLI でプロジェクト保存場所が**分断**している。

### 現状の課題

1. **GUI のプロジェクト保存場所**
   - `config/lorairo.toml` の `[directories] database_base_dir = "lorairo_data"` 参照
   - ディレクトリ構造: `lorairo_data/<name>_<timestamp>/image_database.db`
   - `DirectoryService` 経由でパスを組み立て

2. **CLI のプロジェクト保存場所**
   - `src/lorairo/services/project_management_service.py:37` でハードコード: `Path.home() / ".lorairo" / "projects"`
   - ディレクトリ構造: `~/.lorairo/projects/<name>_<timestamp>/image_database.db`
   - GUI 側と完全に別場所

3. **ユーザー体験の破綻**
   - GUI で作成したプロジェクトが CLI からは見えない (逆も)
   - 同じ `--project foo` を指定しても GUI と CLI で別々の DB に接続
   - Issue #166 の `--project` デッドコード化の一因

### 既存の前提

- GUI は 2025 年 10 月時点から `lorairo_data/` に大量データを蓄積 (18k+ 画像)
- CLI は比較的新しく、`~/.lorairo/projects/` 利用者は少数
- ADR 0009: CLI 環境でも Qt 非依存でサービスを使える設計

## Decision

**プロジェクト保存場所を `lorairo_data/` (より正確には `config/lorairo.toml` の `database_base_dir`) に統一する。**

### 具体的変更

1. `ProjectManagementService.__init__` のデフォルト `projects_base_dir` を変更:

```python
# 変更前
self.projects_base_dir = projects_base_dir or (Path.home() / ".lorairo" / "projects")

# 変更後
from lorairo.utils.config import get_config
self.projects_base_dir = projects_base_dir or Path(get_config().directories.database_base_dir)
```

2. 旧 `~/.lorairo/projects/` の扱い
   - 自動移行は**しない** (ユーザーがデータ配置を把握できる状態を保つ)
   - 初回起動時に旧ディレクトリが存在すれば検出
   - 移行案内ログを出力 (INFO レベル): 「旧ディレクトリが検出されました。`lorairo_data/` への移動を検討してください」

3. `config/lorairo.toml` のコメント更新
   - `database_base_dir` が GUI/CLI 共通のプロジェクト保存場所であることを明記

## Rationale

### 検討した選択肢

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. `lorairo_data/` に統一 | GUI 既存方針に合わせる | **採用** |
| B. `~/.lorairo/projects/` に統一 | XDG ベースのユーザーローカル重視 | 却下 |
| C. 両方サポート (projects テーブルで管理) | 柔軟性重視 | 却下 |

### A を採用した理由

- **既存データの移行コスト最小**: GUI 経由で蓄積された 18k 画像のデータ場所を変えずに済む
- **設定一元化**: `config/lorairo.toml` の `database_base_dir` が唯一の真実に
- **プロジェクト可搬性**: `lorairo_data/` ディレクトリごと別マシンにコピーしてもプロジェクトが移行できる (ユーザーホームに依存しない)
- **開発環境の明示性**: WSL / Docker / native で同じディレクトリ設定が使える (`~` のホーム差異を避けられる)

### B (~/.lorairo/projects/) を却下した理由

- GUI 既存データ (18k 画像) の移行負荷が過大
- ユーザーホーム配置は XDG Base Directory Specification 的には正しいが、プロジェクト単位でのポータビリティが損なわれる
- WSL 環境でホーム配下への大量 I/O は遅い (bind mount のオーバーヘッド)

### C (両方サポート) を却下した理由

- 複雑度が上昇 (2 経路の整合性維持コスト)
- ユーザーが「どこに保存されるか」を予測できない
- ADR 0017 の `projects` テーブルで `path` を記録するため、複数箇所サポートは技術的に可能だが、運用上混乱を招く

## Consequences

### 良い点

- ◎ GUI と CLI が同じプロジェクトにアクセス可能
- ◎ `config/lorairo.toml` が真実の源泉 (設定一元化)
- ◎ プロジェクトディレクトリをまるごとコピー/移動できる (Docker volumes との親和性)
- ◎ 既存 GUI ユーザーへの影響なし

### トレードオフ

- △ 旧 `~/.lorairo/projects/` を使っていた CLI ユーザーは移行必要 (自動移行せず案内のみ)
- △ `lorairo_data/` が相対パスだとカレントディレクトリ依存になる (ADR 0008 の resilience 対策で絶対パス解決するが注意必要)
- △ ユーザーホーム配置を期待する XDG 準拠派からは不満

### 軽減策

- 初回起動時の移行案内ログでユーザーに明示
- `lorairo_data/` 相対パス解決は `get_config().directories.database_base_dir` で一元化 (`Path.resolve()` で絶対化)
- README / CHANGELOG に CLI の保存場所変更を明記

## Related

- Issue #166 (エピック): CLI export create リファクタリング
- Issue #177 [F]: このADRを実装するサブIssue (`ProjectManagementService` 改修)
- ADR 0008: CLAUDE.md Resilience Architecture (絶対パス解決)
- ADR 0009: Qt Decoupling Design (CLI 環境のサービス独立性)
- ADR 0017: Project DB Normalization (`projects.path` カラムがこの統一と整合)
