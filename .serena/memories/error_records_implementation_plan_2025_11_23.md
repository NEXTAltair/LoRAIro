# エラー記録テーブル実装 - 修正実装計画 v2

**作成日**: 2025-11-23  
**対象Issue**: Issue #1（db_manager.py L679, L722 の FIXME）  
**ステータス**: 計画承認待ち

## 📋 計画概要

**目的**: エラー記録テーブルを実装し、GUI からのエラー監視機能を実現する

**重要な前提確認**:
- ✅ 既存 Manager API の後方互換性を完全維持（シグネチャ変更なし）
- ✅ SearchFilterService の未実装メソッドを追加
- ✅ Repository に必要な新規メソッドを明示
- ✅ dataset 単位の集計は第2フェーズ（Phase 5）で対応

**影響範囲**: 
- データベーススキーマ（error_records テーブル追加）
- Repository Layer（エラー記録・取得メソッド6件追加）
- Manager Layer（内部実装のみ変更、APIは維持）
- SearchFilterService（未実装メソッド1件追加）
- GUI Layer（エラーログビューア追加）

**想定工数**: 10-13時間（5フェーズの段階的実装）

---

## 🎯 要件と制約の明確化

### 必須要件
1. ✅ `error_records` テーブルの追加
2. ✅ Manager API の後方互換性維持
3. ✅ SearchFilterService に `get_annotation_status_counts()` 実装
4. ✅ エラー件数が正確に表示される
5. ✅ エラー画像のフィルタリングが動作する

### 設計制約
- ✅ 既存 API シグネチャ変更禁止（GUI/Worker への影響を防止）
- ✅ データ集計は全画像対象（dataset 単位は Phase 5 で対応）
- ✅ `resolved_at TIMESTAMP` で解決状態判定（boolean フラグは使用しない）
- ✅ Repository Pattern 準拠
- ✅ SQLite + Alembic マイグレーション

### 成功基準
1. `ImageDatabaseManager.get_annotation_status_counts()` が既存シグネチャでエラー件数を返す
2. `ImageDatabaseManager.filter_by_annotation_status(error=True)` がエラー画像を返す
3. `SearchFilterService.get_annotation_status_counts()` が `AnnotationStatusCounts` を返す
4. GUI でエラー詳細を確認できる
5. 全テストパス、既存機能に影響なし

---

## 💡 コア設計方針

### 1. 既存 API の完全維持

**Manager API（変更禁止）**:
```python
# シグネチャ維持、内部実装のみ変更
def get_annotation_status_counts(self) -> dict[str, int | float]:
    """既存: パラメータなし、dict返却"""

def filter_by_annotation_status(
    self, completed: bool = False, error: bool = False
) -> list[dict[str, Any]]:
    """既存: bool パラメータ、list[dict]返却"""
```

### 2. SearchFilterService への薄いラッパー追加

```python
# search_filter_service.py に追加（未実装メソッド解消）
def get_annotation_status_counts(self) -> AnnotationStatusCounts:
    """Manager の dict を AnnotationStatusCounts に変換"""
    counts_dict = self.db_manager.get_annotation_status_counts()
    return AnnotationStatusCounts(
        total=counts_dict["total"],
        completed=counts_dict["completed"],
        error=counts_dict["error"]
    )
```

### 3. resolved_at による状態判定

- `resolved_at IS NULL` → 未解決エラー
- `resolved_at IS NOT NULL` → 解決済みエラー
- Repository API は timestamp ベース、boolean は使用しない

### 4. dataset 単位集計は Phase 5 で対応

- Phase 1-4.5: 全画像対象の集計（既存と同じ）
- Phase 5: dataset/directory フィルタ機能追加（将来拡張）

---

## 🏗️ 詳細設計

### 1. データベーススキーマ

```python
class ErrorRecord(Base):
    """処理エラー記録テーブル"""
    __tablename__ = "error_records"
    
    # プライマリキー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # エラー発生コンテキスト
    image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"),
        nullable=True  # 画像未登録時のエラーもあるため
    )
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'registration', 'annotation', 'processing', etc.
    
    # エラー詳細
    error_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'pHash calculation', 'DB constraint', 'File I/O', 'API error', etc.
    error_message: Mapped[str] = mapped_column(String, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(String)
    
    # 追加コンテキスト
    file_path: Mapped[str | None] = mapped_column(String)
    model_name: Mapped[str | None] = mapped_column(String)
    
    # 再試行管理
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    
    # タイムスタンプ
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    image: Mapped[Image | None] = relationship(
        "Image", 
        back_populates="error_records"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_error_records_operation_type", "operation_type"),
        Index("ix_error_records_created_at", "created_at"),
        Index("ix_error_records_resolved", "resolved_at"),
    )
```

**ErrorRecordData TypedDict**:
```python
class ErrorRecordData(TypedDict):
    id: NotRequired[int]
    image_id: int | None
    operation_type: str
    error_type: str
    error_message: str
    stack_trace: NotRequired[str | None]
    file_path: NotRequired[str | None]
    model_name: NotRequired[str | None]
    retry_count: NotRequired[int]
    resolved_at: NotRequired[datetime.datetime | None]
    created_at: NotRequired[datetime.datetime]
```

### 2. Repository Layer - 新規メソッド一覧（6件）

```python
# db_repository.py に追加

def save_error_record(
    self,
    operation_type: str,
    error_type: str,
    error_message: str,
    image_id: int | None = None,
    stack_trace: str | None = None,
    file_path: str | None = None,
    model_name: str | None = None,
) -> int:
    """
    エラーレコードを保存
    
    Returns:
        int: 作成された error_record_id
    """

def get_error_count_unresolved(
    self,
    operation_type: str | None = None
) -> int:
    """
    未解決エラー件数を取得（resolved_at IS NULL）
    
    Args:
        operation_type: 操作種別（None = 全操作）
        
    Returns:
        int: 未解決エラー件数
    """

def get_error_image_ids(
    self,
    operation_type: str | None = None,
    resolved: bool = False
) -> list[int]:
    """
    エラー画像のID一覧を取得
    
    Args:
        operation_type: 操作種別フィルタ
        resolved: True = 解決済み、False = 未解決
        
    Returns:
        list[int]: 画像IDリスト（重複除去済み）
    """

def get_images_by_ids(
    self,
    image_ids: list[int]
) -> list[dict[str, Any]]:
    """
    画像IDリストから画像メタデータを取得
    
    Args:
        image_ids: 画像IDリスト
        
    Returns:
        list[dict]: 画像メタデータリスト（既存フォーマット互換）
    """

def get_error_records(
    self,
    operation_type: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[ErrorRecord]:
    """
    エラーレコードを取得（ページネーション対応）
    
    Args:
        operation_type: 操作種別フィルタ
        resolved: None = 全て、True = 解決済み、False = 未解決
        limit: 取得件数上限
        offset: オフセット
        
    Returns:
        list[ErrorRecord]: エラーレコードリスト
    """

def mark_error_resolved(
    self,
    error_id: int
) -> None:
    """
    エラーを解決済みにマーク（resolved_at = 現在時刻）
    
    Args:
        error_id: エラーレコードID
    """
```

### 3. Manager Layer - 内部実装のみ変更

```python
# db_manager.py の FIXME 解消（シグネチャ変更なし）

def get_annotation_status_counts(self) -> dict[str, int | float]:
    """
    アノテーション状態カウントを取得（既存 API 維持）
    
    Returns:
        dict: {"total": int, "completed": int, "error": int, "completion_rate": float}
    """
    try:
        total_images = self.get_total_image_count()
        
        if total_images == 0:
            return {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}
        
        # 完了画像数（既存ロジック維持）
        session: Session = self.repository.get_session()
        with session:
            completed_query = text("""
                SELECT COUNT(DISTINCT i.id) FROM images i
                LEFT JOIN tags t ON i.id = t.image_id
                LEFT JOIN captions c ON i.id = c.image_id
                WHERE t.id IS NOT NULL OR c.id IS NOT NULL
            """)
            result: Result = session.execute(completed_query)
            completed_images: int = result.scalar() or 0
            
            # ✅ FIXME 解消: エラー画像数を error_records から取得
            error_images = self.repository.get_error_count_unresolved(
                operation_type="annotation"
            )
            
            completion_rate = (completed_images / total_images) * 100.0 if total_images > 0 else 0.0
            
            return {
                "total": total_images,
                "completed": completed_images,
                "error": error_images,
                "completion_rate": completion_rate,
            }
    
    except Exception as e:
        logger.error(f"アノテーション状態カウント取得エラー: {e}", exc_info=True)
        return {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}


def filter_by_annotation_status(
    self, 
    completed: bool = False, 
    error: bool = False
) -> list[dict[str, Any]]:
    """
    アノテーション状態でフィルタリング（既存 API 維持）
    
    Args:
        completed: 完了画像のみ
        error: エラー画像のみ
        
    Returns:
        list[dict]: 画像メタデータリスト
    """
    try:
        session: Session = self.repository.get_session()
        
        with session:
            if completed:
                # 完了画像（既存ロジック維持）
                query = text("""
                    SELECT DISTINCT i.* FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                """)
                result: Result = session.execute(query)
                return [dict(row._mapping) for row in result.fetchall()]
                
            elif error:
                # ✅ FIXME 解消: エラー記録から画像IDを取得
                error_image_ids = self.repository.get_error_image_ids(
                    operation_type="annotation",
                    resolved=False
                )
                
                if not error_image_ids:
                    return []
                
                return self.repository.get_images_by_ids(error_image_ids)
                
            else:
                # 全ての画像（既存ロジック維持）
                query = text("SELECT * FROM images")
                result: Result = session.execute(query)
                return [dict(row._mapping) for row in result.fetchall()]
    
    except Exception as e:
        logger.error(f"アノテーション状態フィルタリングエラー: {e}", exc_info=True)
        return []
```

### 4. SearchFilterService - 未実装メソッド追加

```python
# search_filter_service.py に追加

def get_annotation_status_counts(self) -> AnnotationStatusCounts:
    """
    アノテーション状態カウントを取得（GUI 用）
    
    Returns:
        AnnotationStatusCounts: 状態カウント情報
    """
    try:
        # Manager から dict 取得
        counts_dict = self.db_manager.get_annotation_status_counts()
        
        # AnnotationStatusCounts に変換
        return AnnotationStatusCounts(
            total=counts_dict["total"],
            completed=counts_dict["completed"],
            error=counts_dict["error"]
        )
    
    except Exception as e:
        logger.error(f"状態カウント取得エラー: {e}", exc_info=True)
        return AnnotationStatusCounts()  # デフォルト値（全て0）
```

---

## 📝 実装計画（5フェーズ）

### Phase 1: データベース基盤（2-3時間）

**タスク**:
1. スキーマ定義追加（`schema.py`）
2. Alembic マイグレーション生成・実行
3. Repository メソッド6件実装
4. 単体テスト作成

**成果物**:
- ✅ error_records テーブル作成完了
- ✅ Repository メソッド6件実装完了
- ✅ 単体テスト（pytest -m unit）パス

---

### Phase 2: Manager FIXME 解消（1-2時間）

**タスク**:
1. `get_annotation_status_counts()` 内部実装変更（シグネチャ維持）
2. `filter_by_annotation_status()` 内部クエリ変更（シグネチャ維持）
3. Manager 単体テスト作成
4. 既存テストの回帰確認

**成果物**:
- ✅ Issue #1 FIXME 2箇所解消
- ✅ Manager テストパス
- ✅ 既存機能影響なし確認

---

### Phase 3: SearchFilterService 実装（1時間）

**タスク**:
1. `get_annotation_status_counts()` メソッド追加
2. dict → AnnotationStatusCounts 変換
3. SearchFilterService 単体テスト作成
4. AnnotationStatusFilterWidget の動作確認

**成果物**:
- ✅ SearchFilterService 未実装メソッド解消
- ✅ GUI ウィジェットが動作する
- ✅ テストパス

---

### Phase 4: Worker 統合（2-3時間）

**タスク**:
1. Worker Result オブジェクト拡張
2. Worker エラー保存処理
3. WorkerService シグナル対応
4. 統合テスト作成

**成果物**:
- ✅ Worker エラー自動記録機能
- ✅ 統合テスト（pytest -m integration）パス

---

### Phase 4.5: GUI 実装（3-4時間）

**タスク**:
1. エラーログビューアウィジェット作成
2. エラー詳細モーダル
3. MainWindow への統合
4. GUI テスト作成

**成果物**:
- ✅ エラーログビューア完成
- ✅ MainWindow 統合完了
- ✅ GUI テスト（pytest -m gui）パス

---

### Phase 5: dataset 単位集計対応（将来拡張、今回は実装しない）

**Note**: Phase 5 は Issue #1 の範囲外。将来の機能拡張として別 Issue で管理。

---

## 📊 API 互換性詳細とスコープ定義

### 1. Manager API 互換性整理（シグネチャ完全維持）

**既存API（変更禁止）**:
```python
# db_manager.py L653-693
def get_annotation_status_counts(self) -> dict[str, int | float]:
    """パラメータなし、全画像対象、dictで返却"""
    # 呼び出し元: AnnotationStatusFilterWidget L150 (via SearchFilterService)
    # 戻り値: {"total": int, "completed": int, "error": int, "completion_rate": float}

# db_manager.py L696-732
def filter_by_annotation_status(
    self, completed: bool = False, error: bool = False
) -> list[dict[str, Any]]:
    """boolパラメータ、全画像対象、list[dict]で返却"""
    # 呼び出し元: 現在は直接呼び出しなし（将来のフィルタ機能用）
    # 戻り値: 画像メタデータのdictリスト
```

**影響範囲の検証結果**:
- ✅ `get_annotation_status_counts()`: SearchFilterService経由でGUI呼び出し
- ✅ `filter_by_annotation_status()`: 現在は未使用（将来の拡張用API）
- ✅ シグネチャ変更なし → GUI/Worker側の改修不要

**Phase 2での変更内容**:
```python
# 内部実装のみ変更（シグネチャ維持）
def get_annotation_status_counts(self) -> dict[str, int | float]:
    # 変更前: error_images = 0  # プレースホルダー
    # 変更後:
    error_images = self.repository.get_error_count_unresolved(
        operation_type="annotation"  # アノテーション操作のみ
    )
    return {"total": ..., "completed": ..., "error": error_images, ...}

def filter_by_annotation_status(self, completed: bool = False, error: bool = False):
    if error:
        # 変更前: query = text("SELECT * FROM images WHERE 1=0")
        # 変更後:
        error_image_ids = self.repository.get_error_image_ids(
            operation_type="annotation",  # アノテーション操作のみ
            resolved=False  # 未解決のみ
        )
        return self.repository.get_images_by_ids(error_image_ids)
```

---

### 2. エラー集計のスコープ定義

**Phase 1-4.5（今回実装）**:
- ✅ **全画像対象**: dataset/directoryフィルタなし
- ✅ **操作種別**: "annotation" 操作のみカウント
  - `get_error_count_unresolved(operation_type="annotation")`
  - `get_error_image_ids(operation_type="annotation", resolved=False)`
- ✅ **解決状態**: 未解決のみ（resolved_at IS NULL）

**スコープの根拠**:
```python
# 既存の完了画像カウント（L670-675）
"""
SELECT COUNT(DISTINCT i.id) FROM images i
LEFT JOIN tags t ON i.id = t.image_id
LEFT JOIN captions c ON i.id = c.image_id
WHERE t.id IS NOT NULL OR c.id IS NOT NULL
"""
# → 全画像対象、tagsまたはcaptionsの存在で判定
# → エラーカウントも同様に全画像対象、operation_type="annotation"で絞り込み
```

**Phase 5（将来拡張）**:
- dataset/directory単位の集計
- 操作種別の動的選択
- 日付範囲フィルタ

---

### 3. Repository 新規API完全定義

**追加メソッド6件の詳細**:

```python
# 1. エラーレコード保存
def save_error_record(
    self,
    operation_type: str,  # "registration" | "annotation" | "processing"
    error_type: str,      # "pHash calculation" | "API error" | "DB constraint"
    error_message: str,
    image_id: int | None = None,
    stack_trace: str | None = None,
    file_path: str | None = None,
    model_name: str | None = None,
) -> int:
    """
    Returns:
        int: error_record.id
    
    実装:
        with self.session_factory() as session:
            record = ErrorRecord(
                operation_type=operation_type,
                error_type=error_type,
                error_message=error_message,
                image_id=image_id,
                stack_trace=stack_trace,
                file_path=file_path,
                model_name=model_name,
            )
            session.add(record)
            session.commit()
            return record.id
    """

# 2. 未解決エラー件数
def get_error_count_unresolved(
    self,
    operation_type: str | None = None
) -> int:
    """
    Returns:
        int: 未解決エラー件数
    
    実装:
        with self.session_factory() as session:
            query = select(func.count(ErrorRecord.id)).where(
                ErrorRecord.resolved_at.is_(None)
            )
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            return session.execute(query).scalar() or 0
    """

# 3. エラー画像ID一覧
def get_error_image_ids(
    self,
    operation_type: str | None = None,
    resolved: bool = False
) -> list[int]:
    """
    Args:
        resolved: True = 解決済み（resolved_at IS NOT NULL）
                 False = 未解決（resolved_at IS NULL）
    
    Returns:
        list[int]: 重複除去済みのimage_idリスト（Noneを除外）
    
    実装:
        with self.session_factory() as session:
            query = select(ErrorRecord.image_id).distinct().where(
                ErrorRecord.image_id.is_not(None)
            )
            if resolved:
                query = query.where(ErrorRecord.resolved_at.is_not(None))
            else:
                query = query.where(ErrorRecord.resolved_at.is_(None))
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            return [id for id in session.execute(query).scalars() if id]
    """

# 4. ID指定で画像取得（新規追加）
def get_images_by_ids(
    self,
    image_ids: list[int]
) -> list[dict[str, Any]]:
    """
    Args:
        image_ids: 画像IDリスト
    
    Returns:
        list[dict]: 既存フォーマット互換の画像メタデータ
    
    実装:
        with self.session_factory() as session:
            images = session.execute(
                select(Image).where(Image.id.in_(image_ids))
            ).scalars().all()
            
            return [
                {
                    "id": img.id,
                    "phash": img.phash,
                    "file_path": str(img.file_path),
                    "width": img.width,
                    "height": img.height,
                    # ... 既存のImageDictフォーマット
                }
                for img in images
            ]
    
    Note: 既存の get_images_by_filter() の戻り値フォーマットに準拠
    """

# 5. エラーレコード検索
def get_error_records(
    self,
    operation_type: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[ErrorRecord]:
    """
    Args:
        resolved: None = 全て、True = 解決済み、False = 未解決
    
    Returns:
        list[ErrorRecord]: ORMオブジェクトのリスト
    
    実装:
        with self.session_factory() as session:
            query = select(ErrorRecord).order_by(
                ErrorRecord.created_at.desc()
            )
            if operation_type:
                query = query.where(ErrorRecord.operation_type == operation_type)
            if resolved is not None:
                if resolved:
                    query = query.where(ErrorRecord.resolved_at.is_not(None))
                else:
                    query = query.where(ErrorRecord.resolved_at.is_(None))
            query = query.limit(limit).offset(offset)
            return list(session.execute(query).scalars())
    """

# 6. 解決済みマーク
def mark_error_resolved(
    self,
    error_id: int
) -> None:
    """
    実装:
        with self.session_factory() as session:
            record = session.get(ErrorRecord, error_id)
            if record:
                record.resolved_at = func.now()
                session.commit()
    """
```

**必要なTypeDict（schema.pyに追加）**:
```python
class ErrorRecordData(TypedDict):
    """エラーレコードデータ型"""
    id: NotRequired[int]
    image_id: int | None
    operation_type: str
    error_type: str
    error_message: str
    stack_trace: NotRequired[str | None]
    file_path: NotRequired[str | None]
    model_name: NotRequired[str | None]
    retry_count: NotRequired[int]
    resolved_at: NotRequired[datetime.datetime | None]
    created_at: NotRequired[datetime.datetime]
```

---

### 4. 解決状態フラグの完全整合

**スキーマ定義（booleanカラムなし）**:
```python
class ErrorRecord(Base):
    # ...
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    # ❌ resolved: Mapped[bool] は定義しない
```

**Repository API（timestampベース）**:
```python
# ✅ 正しい使い方
def get_error_image_ids(
    self,
    operation_type: str | None = None,
    resolved: bool = False  # API引数はbool（内部でtimestamp判定）
) -> list[int]:
    # 内部実装でtimestampに変換
    if resolved:
        query = query.where(ErrorRecord.resolved_at.is_not(None))
    else:
        query = query.where(ErrorRecord.resolved_at.is_(None))
```

**状態判定ロジック統一**:
```python
# 未解決エラー
WHERE resolved_at IS NULL

# 解決済みエラー
WHERE resolved_at IS NOT NULL

# 解決済みにマーク
UPDATE error_records 
SET resolved_at = CURRENT_TIMESTAMP 
WHERE id = ?

# ❌ 使用禁止
WHERE resolved = TRUE  # resolvedカラムは存在しない
```

**API層とDB層の対応**:
| API引数 | DB条件 | 意味 |
|--------|-------|------|
| `resolved=False` | `resolved_at IS NULL` | 未解決エラー |
| `resolved=True` | `resolved_at IS NOT NULL` | 解決済みエラー |
| `resolved=None` | 条件なし | 全てのエラー |

---

## API互換性マトリクス

| メソッド | 既存シグネチャ | 変更 | 影響範囲 | GUI改修 |
|---------|--------------|------|---------|---------|
| `ImageDatabaseManager.get_annotation_status_counts()` | `() -> dict[str, int \| float]` | 内部実装のみ | なし | 不要 |
| `ImageDatabaseManager.filter_by_annotation_status()` | `(completed: bool, error: bool) -> list[dict]` | 内部実装のみ | なし | 不要 |
| `SearchFilterService.get_annotation_status_counts()` | **新規追加** | - | AnnotationStatusFilterWidget | 不要（既に呼び出しコードあり） |
| `ImageRepository.save_error_record()` | **新規追加** | - | Worker | Phase 4で追加 |
| `ImageRepository.get_error_count_unresolved()` | **新規追加** | - | Manager | Phase 2で追加 |
| `ImageRepository.get_error_image_ids()` | **新規追加** | - | Manager | Phase 2で追加 |
| `ImageRepository.get_images_by_ids()` | **新規追加** | - | Manager | Phase 2で追加 |
| `ImageRepository.get_error_records()` | **新規追加** | - | GUI | Phase 4.5で追加 |
| `ImageRepository.mark_error_resolved()` | **新規追加** | - | GUI | Phase 4.5で追加 |

---------|--------------|------|---------|
| `ImageDatabaseManager.get_annotation_status_counts()` | `() -> dict[str, int \| float]` | 内部実装のみ | なし |
| `ImageDatabaseManager.filter_by_annotation_status()` | `(completed: bool, error: bool) -> list[dict]` | 内部実装のみ | なし |
| `SearchFilterService.get_annotation_status_counts()` | **新規追加** | - | AnnotationStatusFilterWidget |

---

## ⚠️ リスク分析と対策

### リスク1: 既存 API 互換性の破壊

**影響**: GUI/Worker が動作しなくなる  
**確率**: 低（シグネチャ維持）  
**対策**: シグネチャ変更禁止、戻り値フォーマット維持、既存テストで回帰確認

### リスク2: SearchFilterService 統合の複雑化

**影響**: GUI エラー表示の不具合  
**確率**: 中（未実装メソッド追加）  
**対策**: 薄いラッパー実装（変換のみ）、Manager API に依存、単体テストで変換確認

### リスク3: resolved_at の誤用

**影響**: エラー状態判定の誤り  
**確率**: 低  
**対策**: boolean フラグを使用しない、`IS NULL` / `IS NOT NULL` で判定、テストで timestamp ベース検証

### リスク4: dataset 単位集計の期待

**影響**: ユーザーが dataset フィルタを期待  
**確率**: 中  
**対策**: Phase 5 で対応と明記、現時点では全画像対象と説明、将来拡張の設計余地を確保

---

## 📚 状態判定ロジック

```python
# resolved_at による状態判定（boolean 使用禁止）

# 未解決エラー
WHERE resolved_at IS NULL

# 解決済みエラー
WHERE resolved_at IS NOT NULL

# 解決済みにマーク
UPDATE error_records 
SET resolved_at = NOW() 
WHERE id = ?
```

---

## 🔄 Phase 5（将来拡張）への移行パス

**現状（Phase 4.5完了時）**:
- ✅ 全画像対象のエラー集計
- ✅ 操作種別フィルタ
- ✅ 解決状態フィルタ

**Phase 5 で追加**:
- dataset/directory 単位の集計
- Manager API に dataset_id パラメータ追加
- error_records に dataset 情報カラム追加
- GUI で dataset 切り替え

**移行時の互換性**:
- Phase 4.5 の API は維持
- dataset_id は Optional パラメータとして追加
- デフォルトは全画像対象（既存動作）
