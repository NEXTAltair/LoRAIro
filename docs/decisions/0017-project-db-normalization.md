---
type: ADR
title: Project DB Normalization
status: Implemented (2026-04-25)
timestamp: 2026-04-22
tags: []
---
# ADR 0017: Project DB Normalization

## Context

LoRAIro では「プロジェクト」という概念が複数の機能境界にわたって使われている。しかしデータベース層では、**プロジェクトが第一級エンティティとして表現されていない**。

### 現状の課題

1. **スキーマ上の不在**
   - `src/lorairo/database/schema.py` に `projects` テーブルが存在しない。
   - `Image` テーブルに `project_id` 外部キー相当のカラムがない。
   - プロジェクトはファイルシステムのディレクトリ構造(`lorairo_data/<name>_<timestamp>/image_database.db`)のみで管理されている。

2. **機能的な破綻(Issue #165、#166)**
   - `src/lorairo/api/export.py:13-42` の `_resolve_project_image_ids()` は、ファイルシステム走査の結果から `list(range(len(image_files)))` を返している。これは DB 上の実際の `image_id` とは無関係なダミー実装である。
   - `src/lorairo/cli/commands/export.py:95` の `repository.get_images_by_filter()` は引数なしで呼ばれており、全件取得になっている。そのため、`--project foo` を指定しても 21,029 件の全画像が返ってしまう。
   - 両問題の根本原因は、プロジェクト名から `image_id` 一覧を引く DB メソッドが存在しない点にある。

3. **既存の教訓**
   - **ADR 0002**:`genai-tag-db-tools` 由来の `tag_id` など、外部 DB に対する FK 制約は避ける方針である。しかし LoRAIro 内部スキーマ同士であれば FK で表現でき、避ける理由はない。
   - **ADR 0006**:全件取得は深刻な性能問題を引き起こす(18,252 件の全件取得問題は LIMIT/OFFSET で解決済み)。
   - **ADR 0015**:二重管理はデータの乖離を招く(手動レーティングの書き込み・読み込み非対称バグの教訓)。

## Decision

LoRAIro の DB スキーマを拡張し、プロジェクトを第一級エンティティとして正規化する。

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

1. `projects` テーブルを単独で作成する(非破壊変更)。
2. `batch_alter_table` を使って `images.project_id` カラムを追加する(互換性のため `nullable=True` とする)。
3. 既存データに対するバックフィルを実施する。
   - `config/lorairo.toml` の `[directories] database_base_dir` からプロジェクトルートを検出する。
   - ディレクトリ名(`main_dataset_20250707_001` 等)からプロジェクト名を抽出する。
   - `projects` テーブルへ INSERT し、全レコードの `images.project_id` を一括 UPDATE する。
4. 冪等性を確保するため、`SELECT COUNT(*) FROM projects` で既存行がある場合はバックフィルをスキップする。

## Rationale

### 検討した選択肢

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A:`projects` テーブル追加による正規化 | 第一級エンティティとして表現する | **採用** |
| B:ファイルパスマッチによる暫定フィルタ | `Image.stored_image_path.like(f"%{project}%")` で絞り込む | 却下 |
| C:JSON カラムへの格納 | `Image.metadata` JSON 内にプロジェクト情報を記録する | 却下 |

### A を採用した理由

- **ADR 0015 の「二重管理禁止」原則への準拠**:ファイルシステムと DB で情報が二重化するのを避け、DB を単一の真実の源泉(SSoT)とできる。
- **ADR 0006 の「全件取得の回避」に対する根本対策**:プロジェクト検索時の `WHERE project_id = ?` がインデックスによって O(log n) で実行できる。
- **Issue #165 の正攻法での解決**:ダミー ID 生成を DB 連携の実装へ置き換えられる。
- **リレーションの表現力**:「1 プロジェクト対 N 画像」という自然な関係を型安全に表現できる。

### B (LIKE 句マッチ) を却下した理由

- `LIKE "%foo%"` はインデックスが効かず全表スキャンになる(タグ検索での教訓)。
- `stored_image_path` の文字列構造に依存するため、パス変更によって容易に壊れる。
- 本質的に Issue #165 と同じ暫定的な実装を残すことになる。

### C (JSON カラム) を却下した理由

- SQLite での JSON 検索は記述が複雑になり、処理速度も低下する。
- JOIN で表現できないため、将来プロジェクトのメタデータを拡張する際に負担が大きくなる。
- スキーマレス化によって、アプリケーションコード側の検証負担が増える。

## Consequences

### 良い点

- インデックス付き FK により、プロジェクト単位のフィルタリングが高速に動作する。
- Issue #165 と Issue #166 の共通原因を根本から解決できる。
- 将来的なプロジェクト単位の集計(画像数、最終更新日など)を自然に実装できる。
- CLI の `--project foo` が、初めて本来のプロジェクトフィルタとして機能するようになる。

### トレードオフ

- スキーマ変更を伴うため、Alembic マイグレーションの実行が必須になる。
- `ON DELETE SET NULL` を設定しているため、プロジェクト削除時に画像が孤児化する(データ自体は消失しないが、`project_id=NULL` になる)。
- **既存データ(18k 画像)のバックフィルが失敗するリスク**がある。

### 軽減策

- マイグレーション実行前に、`make backup` による `.7z` バックアップを強制する。
- Alembic に `dry-run` オプションを追加する。
- CI で `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` のラウンドトリップ検証を必須化する。
- バックフィルに冪等性(既存 `projects` 行があればスキップ)を持たせ、再実行時の安全性を確保する。

## Related

- Issue #166(エピック):CLI `export create` リファクタリング
- Issue #165:`_resolve_project_image_ids()` のダミー実装
- Issue #175 [C]:本 ADR を実装するサブ Issue
- ADR 0002: Database Schema Decisions(外部 FK 制約なし方針)
- ADR 0006: Pagination Approach(全件取得の危険性)
- ADR 0015: Manual Rating Storage Unification(二重管理禁止)
- ADR 0018: Project Storage Unification(プロジェクト保存場所の統一)
