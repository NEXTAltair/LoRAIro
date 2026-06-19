---
type: ADR
title: Repository Aggregate分割方針
status: Accepted
timestamp: 2026-05-25
tags: []
---
# ADR 0035: Repository Aggregate分割方針

- **関連 Issue**: #426 (ADR起票), #423 (実装)

## Context

`src/lorairo/database/db_repository.py` が **3,902 行・80+ メソッドの単一クラス `ImageRepository`** に成長した。
複数 entity (Image / ProcessedImage / Annotation×4 / Tag / Model / Project / ErrorRecord / FilenameAlias / Batch) の
責務が 1 クラスに混在し、Single Responsibility 原則に強く違反している。

具体的な問題:

- 変更理由が複数ある（例: Model 周りの変更が Annotation テストを壊しうる）
- テスト時のモックが粗粒度になる（`Mock(spec=ImageRepository)` に全 80+ メソッドが乗る）
- genai-tag-db-tools 連携コード (`MergedTagReader`, `TagRegisterService`) がクラス初期化に直結し
  Annotation 以外の操作でも初期化が走る

## Decision

### 1. 分割単位: Aggregate 単位の 5 Repository

`ImageRepository` を以下の 5 クラスに分割する。
各クラスは `src/lorairo/database/repository/` ディレクトリに配置する。

| クラス | ファイル | 管轄 entity |
|---|---|---|
| `ImageRepository` | `image.py` | `Image`, `ProcessedImage`, `FilenameAlias` |
| `ModelRepository` | `model.py` | `Model`, `ModelType`, モデル関連アソシエーション |
| `AnnotationRepository` | `annotation.py` | `Tag`, `Caption`, `Score`, `ScoreLabel`, `Rating`, genai-tag-db-tools 連携 |
| `ProjectRepository` | `project.py` | `Project`, `ImageProject` (FK) |
| `ErrorRecordRepository` | `error_record.py` | `ErrorRecord` |

### 2. 共通基盤: BaseRepository

```python
# src/lorairo/database/repository/base.py
class BaseRepository:
    def __init__(self, session_factory: Callable[[], Session] = DefaultSessionLocal) -> None:
        self.session_factory = session_factory
```

各 Repository は `BaseRepository` を継承する。
`BATCH_CHUNK_SIZE` など全体定数は `base.py` に移動する。

### 3. ImageDatabaseManager との関係

`ImageDatabaseManager` は 5 Repository を **composition** で保持する。

```python
class ImageDatabaseManager:
    def __init__(
        self,
        session_factory: Callable[[], Session] = DefaultSessionLocal,
    ) -> None:
        self.image_repo = ImageRepository(session_factory)
        self.model_repo = ModelRepository(session_factory)
        self.annotation_repo = AnnotationRepository(session_factory)
        self.project_repo = ProjectRepository(session_factory)
        self.error_record_repo = ErrorRecordRepository(session_factory)
```

Manager の畳み込み（廃止）は本 ADR のスコープ外とし、#422 のエラーハンドリング統一と同時に判断する。

### 4. genai-tag-db-tools 連携の置き場

`MergedTagReader` と `TagRegisterService` の初期化・保持は **`AnnotationRepository`** に移動する。
Annotation 以外の Repository からは参照しない。

### 5. import 互換: 段階移行ファサード

`src/lorairo/database/db_repository.py` は **既存のシンボルを全て re-export するファサード** として残す。
これにより `ImageDatabaseManager` や既存 import を壊さずに段階移行できる。

```python
# db_repository.py (移行期間中)
from lorairo.database.repository.image import ImageRepository as ImageRepository
from lorairo.database.repository.model import ModelRepository as ModelRepository
# ... (全シンボルを re-export)
```

移行完了後、ファサードは deprecated → 削除する。

### 6. 移行戦略

entity ごとに PR を分割して段階的に移行する（推奨順）:

1. `ModelRepository` 分割（他 entity への依存が少ない）
2. `ProjectRepository` 分割
3. `ErrorRecordRepository` 分割
4. `ImageRepository` 分割
5. `AnnotationRepository` 分割（genai-tag-db-tools 連携を含む、最も複雑）

## Rationale

**単一クラス維持案（却下）**: 80+ メソッドを抱えたままではテスト境界が粗すぎる。
モックが意図しないメソッドを暴露しており、テストの信頼性が低下している。

**ファイル分割のみ案（却下）**: クラスを分割せず複数ファイルに分けると、
循環 import や session_factory の受け渡しが複雑になる。クラス境界で責務を表現すべき。

**Aggregate 5分割案（採用）**: entity 境界が明確で、Manager からの DI も自然。
genai-tag-db-tools 連携を AnnotationRepository に局所化できる。

## Consequences

**良い点:**
- 各 Repository を `Mock(spec=XxxRepository)` で独立モック可能
- `AnnotationRepository` のみ genai-tag-db-tools を初期化するため起動コスト低減
- 変更範囲が entity 単位に局所化される

**悪い点:**
- `ImageDatabaseManager` のコンストラクタが 5 引数化し、テスト fixture が増える
- 段階移行期間中は db_repository.py ファサードが余計なインポートを持つ

**トレードオフ:**
- Manager 畳み込みは #422 と同時に判断する。本 ADR では Manager を維持したまま
  Repository を分割し、段階的に整理する。

## Related

- #423 (実装: db_repository.py god class 分割)
- #422 (Manager 層エラーハンドリング統一 → ADR 0037)
- ADR 0001 (Two-Tier Service Architecture — Data Layer 定義)
- ADR 0002 (Database Schema Decisions)