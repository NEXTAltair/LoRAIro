---
type: ADR
title: Repository Aggregate分割方針
status: Accepted
timestamp: 2026-05-25
tags: []
---
# ADR 0035: Repository Aggregate分割方針

- **関連 Issue**: #426(ADR 起票)、#423(実装)

## Context

`src/lorairo/database/db_repository.py` は、**3,902 行・80 以上のメソッドを抱える単一クラス `ImageRepository`** へと肥大化した。複数のエンティティ(`Image`、`ProcessedImage`、4 種の `Annotation`、`Tag`、`Model`、`Project`、`ErrorRecord`、`FilenameAlias`、`Batch`)の責務が 1 クラスに混在しており、単一責任原則に大きく違反している。

この構造により、以下の問題が顕在化している。

- クラスを変更する理由が複数存在する(例:Model 周りの変更が Annotation テストを壊す恐れがある)。
- テスト時のモック粒度が粗くなり、`Mock(spec=ImageRepository)` に 80 以上の全メソッドが載ってしまう。
- `genai-tag-db-tools` 連携コード(`MergedTagReader`、`TagRegisterService`)がクラス初期化に直結しており、Annotation 以外の操作でも初期化が実行される。

## Decision

### 1. 分割単位:集約(Aggregate)単位の 5 Repository

`ImageRepository` を以下の 5 クラスに分割し、各クラスを `src/lorairo/database/repository/` ディレクトリ配下に配置する。

| クラス | ファイル | 管轄エンティティ |
|---|---|---|
| `ImageRepository` | `image.py` | `Image`, `ProcessedImage`, `FilenameAlias` |
| `ModelRepository` | `model.py` | `Model`, `ModelType`, モデル関連アソシエーション |
| `AnnotationRepository` | `annotation.py` | `Tag`, `Caption`, `Score`, `ScoreLabel`, `Rating`, `genai-tag-db-tools` 連携 |
| `ProjectRepository` | `project.py` | `Project`, `ImageProject`(FK) |
| `ErrorRecordRepository` | `error_record.py` | `ErrorRecord` |

### 2. 共通基盤:`BaseRepository`

各 Repository の共通基底クラスとして `BaseRepository` を設ける。

```python
# src/lorairo/database/repository/base.py
class BaseRepository:
    def __init__(self, session_factory: Callable[[], Session] = DefaultSessionLocal) -> None:
        self.session_factory = session_factory
```

各 Repository は `BaseRepository` を継承する。`BATCH_CHUNK_SIZE` などの全体定数も `base.py` へ移動する。

### 3. `ImageDatabaseManager` との関係

`ImageDatabaseManager` は、分割した 5 つの Repository を**コンポジション**によって保持する。

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

`ImageDatabaseManager` 自体の畳み込み(廃止)は本 ADR の対象外とする。その是非は、#422 におけるエラーハンドリング統一とあわせて判断する。

### 4. `genai-tag-db-tools` 連携の配置先

`MergedTagReader` と `TagRegisterService` の初期化および保持は、**`AnnotationRepository`** に移す。Annotation 以外の Repository からはこれらを参照しない。

### 5. インポート互換:段階移行用ファサード

`src/lorairo/database/db_repository.py` は、**既存の全シンボルを再エクスポートするファサード**として維持する。これにより、`ImageDatabaseManager` や既存のインポート箇所を壊さずに段階的な移行を進められる。

```python
# db_repository.py (移行期間中)
from lorairo.database.repository.image import ImageRepository as ImageRepository
from lorairo.database.repository.model import ModelRepository as ModelRepository
# ... (全シンボルを re-export)
```

移行完了後、このファサードは非推奨(deprecated)としたうえで削除する。

### 6. 移行戦略

エンティティごとに PR を分割し、以下の推奨順で段階的に移行する。

1. `ModelRepository` の分割(他エンティティへの依存が少ないため)
2. `ProjectRepository` の分割
3. `ErrorRecordRepository` の分割
4. `ImageRepository` の分割
5. `AnnotationRepository` の分割(`genai-tag-db-tools` 連携を含み、最も複雑なため)

## Rationale

以下の 3 案を比較検討した。

- **単一クラス維持案(却下)**:80 以上のメソッドを抱えたままではテスト境界が粗すぎる。モックが意図しないメソッドまで露出してしまい、テストの信頼性が低下する。
- **ファイル分割のみ案(却下)**:クラスを分割せずに複数ファイルへ分けると、循環インポートや `session_factory` の受け渡しが複雑化する。責務の分離はクラス境界で表現すべきである。
- **Aggregate 5 分割案(採用)**:エンティティ境界が明確になり、Manager からの依存注入も自然になる。さらに、`genai-tag-db-tools` 連携を `AnnotationRepository` に局所化できる。

## Consequences

### 良い点

- 各 Repository を `Mock(spec=XxxRepository)` で独立してモック化できる。
- `AnnotationRepository` だけが `genai-tag-db-tools` を初期化するため、起動コストを低減できる。
- 変更の影響範囲がエンティティ単位に局所化される。

### 悪い点

- `ImageDatabaseManager` の初期化対象が 5 つの Repository に増えるため、テスト用フィクスチャが増える。
- 段階移行期間中は、`db_repository.py` ファサードが移行用のインポートを保持し続ける。

### トレードオフ

`ImageDatabaseManager` の畳み込みは #422 と同時に判断する。本 ADR では Manager 層を維持したまま Repository を分割し、段階的に整理する方針を採る。

## Related

- #423(実装:`db_repository.py` 巨大クラスの分割)
- #422(Manager 層エラーハンドリング統一 → ADR 0037)
- ADR 0001(Two-Tier Service Architecture — Data Layer の定義)
- ADR 0002(Database Schema Decisions)
