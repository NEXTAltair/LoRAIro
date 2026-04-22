# ADR 0017: Project DB Normalization

- **日付**: 2026-04-22
- **ステータス**: Accepted

## Context

LoRAIro では「プロジェクト」概念が複数の機能境界に渡って使われているが、データベース層では**プロジェクトを第一級エンティティとして表現していない**。

### 現状の課題

1. **スキーマ上の不在**
   - `projects` テーブルが存在しない (`src/lorairo/database/schema.py`)
   - `Image` テーブルに `project_id` FK 相当のカラムが無い
   - プロジェクトはファイルシステムディレクトリ構造のみで管理 (`lorairo_data/<name>_<timestamp>/image_database.db`)

2. **機能的破綻 (Issue #165 / #166)**
   - `src/lorairo/api/export.py:13-42` の `_resolve_project_image_ids()` がファイルシステム走査で `list(range(len(image_files)))` を返す (DB 上の実 image_id と無関係なダミー実装)
   - `src/lorairo/cli/commands/export.py:95` の `repository.get_images_by_filter()` が引数無し呼び出しで全件取得。`--project foo` 指定でも 21,029 件の全画像が返る
   - 両問題とも根本原因は「プロジェクト名 → image_id 一覧」の DB メソッド不在

3. **既存の教訓**
   - ADR 0002: 外部 FK 制約を避ける方針 (genai-tag-db-tools 由来の tag_id 等)。しかし LoRAIro 内部スキーマでは FK 表現可能で避ける理由はない
   - ADR 0006: 全件取得はパフォーマンス問題を引き起こす (18,252 件全件取得 → LIMIT/OFFSET で解決済)
   - ADR 0015: 二重管理はデータ乖離を招く (手動 rating の書込/読込対称性バグ)

## Decision

LoRAIro DB スキーマを拡張し、プロジェクトを第一級エンティティとして正規化する。

### スキーマ追加

```python
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    path: Mapped[str] = mapped_column(String, nullable=False)  # 絶対パス
    description: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    images: Mapped[list["Image"]] = relationship("Image", back_populates="project")


class Image(Base):
    # 既存フィールドに追加
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project: Mapped["Project | None"] = relationship("Project", back_populates="images")
```

### Repository メソッド追加

```python
def get_image_ids_by_project(self, project_name: str) -> list[int]: ...
def get_image_ids_by_project_id(self, project_id: int) -> list[int]: ...
def ensure_project(self, name: str, path: Path, description: str = "") -> int:
    """プロジェクト upsert (name UNIQUE)。ID を返す。"""
def assign_images_to_project(self, image_ids: list[int], project_id: int) -> int: ...
```

### Alembic マイグレーション戦略

1. `projects` テーブル単独 CREATE (非破壊)
2. `batch_alter_table` で `images.project_id` カラム追加 (nullable=True で互換)
3. データ遡及バックフィル:
   - `config/lorairo.toml` の `[directories] database_base_dir` からプロジェクトルートを検出
   - ディレクトリ名 (`main_dataset_20250707_001` 等) から name 抽出
   - `projects` に INSERT、全 `images.project_id` を bulk UPDATE
4. 冪等性: `SELECT COUNT(*) FROM projects` で既存行あれば skip

## Rationale

### 検討した選択肢

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. `projects` テーブル追加で正規化 | 第一級エンティティとして表現 | **採用** |
| B. ファイルパスマッチで暫定フィルタ | `Image.stored_image_path.like(f"%{project}%")` | 却下 |
| C. プロジェクト情報を JSON カラムに格納 | `Image.metadata` JSON 内に project 記録 | 却下 |

### A を採用した理由

- **ADR 0015 の「二重管理禁止」原則準拠**: ファイルシステムと DB の二重真実を避け、DB を真実の源泉とする
- **ADR 0006 の「全件取得は危険」への根本対策**: プロジェクト名検索の `WHERE project_id = ?` がインデックスで O(log n) になる
- **Issue #165 の正攻法解決**: ダミー ID 生成を DB 連携に置き換えられる
- **リレーション表現力**: 1 プロジェクト N 画像という自然な関係を型で表現可能

### B (LIKE 句マッチ) を却下した理由

- `LIKE "%foo%"` はインデックスが効かず全表スキャン (タグ検索の教訓)
- `stored_image_path` の文字列構造に依存 → パス変更で壊れる
- 結局 Issue #165 と同じダミー性を残す

### C (JSON カラム) を却下した理由

- SQLite JSON 検索は複雑で遅い
- JOIN 表現不可 → Project メタデータ拡張時に痛む
- スキーマレス化はコード側の検証負担増

## Consequences

### 良い点

- ◎ プロジェクト単位のフィルタが高速 (インデックス付き FK)
- ◎ Issue #165 / #166 の同根問題を根本解決
- ◎ 将来的な Project レベルの集計 (画像数、最終更新日等) が自然に書ける
- ◎ CLI の `--project foo` が初めて「本物」のプロジェクトフィルタになる

### トレードオフ

- △ スキーマ変更による破壊的変更 (Alembic マイグレーション必須)
- △ `ON DELETE SET NULL` のため、プロジェクト削除時に画像が孤児化する (データ消失はしないが `project_id=NULL` になる)
- ✗ **既存データ (18k 画像) のバックフィル失敗リスク**

### 軽減策

- マイグレーション実行前に `.7z` 強制バックアップ (`make backup`)
- Alembic の `dry-run` オプション追加
- CI で `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` のラウンドトリップ必須化
- バックフィルの冪等性 (既存 projects 行あれば skip) で再実行安全

## Related

- Issue #166 (エピック): CLI export create リファクタリング
- Issue #165: `_resolve_project_image_ids()` ダミー実装
- Issue #175 [C]: このADRを実装するサブIssue
- ADR 0002: Database Schema Decisions (外部 FK 制約なし方針)
- ADR 0006: Pagination Approach (全件取得の危険性)
- ADR 0015: Manual Rating Storage Unification (二重管理禁止)
- ADR 0018: Project Storage Unification (プロジェクト保存場所)
