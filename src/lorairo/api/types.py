"""LoRAIro API層のデータ型定義。

Pydantic モデルを使用してバリデーション付きのデータ型を定義し、
型安全性とドキュメント生成を実現する。
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ==================== プロジェクト関連 ====================


class ProjectCreateRequest(BaseModel):
    """プロジェクト作成リクエスト。

    Attributes:
        name: プロジェクト名（アルファベット・数字・アンダースコア、1-64文字）。
        description: プロジェクトの説明（任意）。
    """

    name: str = Field(
        ..., min_length=1, max_length=64,
        description="プロジェクト名"
    )
    description: str | None = Field(
        default=None, max_length=256,
        description="プロジェクトの説明"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """プロジェクト名の形式検証。"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "プロジェクト名はアルファベット・数字・アンダースコア・"
                "ハイフンのみ使用可能です"
            )
        return v


class ProjectInfo(BaseModel):
    """プロジェクト情報。

    Attributes:
        name: プロジェクト名。
        path: プロジェクトディレクトリのパス。
        created: 作成日時。
        description: プロジェクトの説明。
        image_count: プロジェクト内の画像枚数。
    """

    name: str
    path: Path
    created: datetime
    description: str | None = None
    image_count: int = 0


# ==================== 画像関連 ====================


class ImageMetadata(BaseModel):
    """画像メタデータ。

    Attributes:
        id: 画像ID。
        file_path: 画像ファイルパス。
        phash: 知覚ハッシュ値。
        width: 画像幅（ピクセル）。
        height: 画像高さ（ピクセル）。
        added_date: データベース登録日時。
        tags: タグリスト。
        captions: キャプション（AI生成テキスト）のリスト。
    """

    id: int
    file_path: Path
    phash: str
    width: int
    height: int
    added_date: datetime
    tags: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)


class RegistrationResult(BaseModel):
    """画像登録結果。

    Attributes:
        total: 処理対象の全画像枚数。
        successful: 登録成功枚数。
        failed: 登録失敗枚数。
        skipped: スキップされた（重複など）枚数。
        error_details: エラー詳細情報のリスト（任意）。
    """

    total: int
    successful: int
    failed: int
    skipped: int
    error_details: list[str] | None = None

    @property
    def success_rate(self) -> float:
        """成功率を計算（0.0-1.0）。"""
        if self.total == 0:
            return 0.0
        return self.successful / self.total


class DuplicateInfo(BaseModel):
    """重複画像情報。

    Attributes:
        file_path: ファイルパス。
        existing_id: 既に登録されている画像ID。
        similarity: 類似度（0.0-1.0、pHashマッチの場合は1.0）。
    """

    file_path: Path
    existing_id: int
    similarity: float


# ==================== アノテーション関連 ====================


class AnnotationResult(BaseModel):
    """アノテーション実行結果。

    Attributes:
        image_count: アノテーション実行の画像枚数。
        successful_annotations: 成功したアノテーション数。
        failed_annotations: 失敗したアノテーション数。
        results: アノテーション結果（モデルごと、形式は
                 PHashAnnotationResults に準拠）。
    """

    image_count: int
    successful_annotations: int
    failed_annotations: int
    results: dict[str, Any] | None = None

    @property
    def success_rate(self) -> float:
        """成功率を計算（0.0-1.0）。"""
        if self.image_count == 0:
            return 0.0
        return self.successful_annotations / self.image_count


class ModelInfo(BaseModel):
    """モデル情報。

    Attributes:
        name: モデル名。
        provider: プロバイダー（'openai', 'claude', 'google', 'local' など）。
        requires_api_key: API キーが必須かどうか。
    """

    name: str
    provider: str
    requires_api_key: bool


# ==================== エクスポート関連 ====================


class ExportResult(BaseModel):
    """データセットエクスポート結果。

    Attributes:
        output_path: 出力ディレクトリパス。
        file_count: エクスポートされたファイル枚数。
        total_size: 合計ファイルサイズ（バイト）。
        format_type: エクスポート形式（'txt', 'json' など）。
        resolution: エクスポートされた画像解像度（ピクセル）。
    """

    output_path: Path
    file_count: int
    total_size: int
    format_type: str
    resolution: int | None = None

    @property
    def total_size_mb(self) -> float:
        """合計サイズを MB 単位で取得。"""
        return self.total_size / (1024 * 1024)


class ExportCriteria(BaseModel):
    """エクスポート条件。

    Attributes:
        format_type: エクスポート形式（'txt', 'json'）。
        resolution: 出力画像の解像度（ピクセル）。
        include_captions: キャプションを含めるかどうか。
        include_tags: タグを含めるかどうか。
        tag_filter: タグフィルター（指定タグのみをエクスポート）。
    """

    format_type: str = Field(default="txt", pattern="^(txt|json)$")
    resolution: int = Field(default=512, ge=256, le=2048)
    include_captions: bool = True
    include_tags: bool = True
    tag_filter: list[str] | None = None


# ==================== タグ関連 ====================


class TagSearchResult(BaseModel):
    """タグ検索結果。

    Attributes:
        query: 検索クエリ。
        matches: マッチしたタグのリスト。
        count: マッチ数。
    """

    query: str
    matches: list[str]
    count: int


class TagInfo(BaseModel):
    """タグ情報。

    Attributes:
        name: タグ名。
        type_name: タグ種類（'character', 'copyright', 'unknown' など）。
        count: プロジェクト内での使用数。
    """

    name: str
    type_name: str
    count: int = 0


# ==================== ページング関連 ====================


class PaginationInfo(BaseModel):
    """ページング情報。

    Attributes:
        total: 全アイテム数。
        page: 現在のページ番号（1ベース）。
        per_page: 1ページあたりのアイテム数。
    """

    total: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    @property
    def total_pages(self) -> int:
        """全ページ数を計算。"""
        if self.total == 0:
            return 1
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def offset(self) -> int:
        """オフセットを計算（0ベース）。"""
        return (self.page - 1) * self.per_page


class PagedResult(BaseModel):
    """ページ化されたリスト結果。

    Type variable で結果型を指定することを想定。

    Attributes:
        items: このページのアイテムのリスト。
        pagination: ページング情報。
    """

    items: list[dict[str, Any]]
    pagination: PaginationInfo


# ==================== ユーティリティ型 ====================


class StatusResponse(BaseModel):
    """API ステータスレスポンス。

    Attributes:
        success: 操作が成功したかどうか。
        message: ステータスメッセージ。
        data: 追加データ（任意）。
    """

    success: bool
    message: str
    data: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """API エラーレスポンス。

    Attributes:
        error_code: エラーコード。
        error_message: エラーメッセージ。
        details: エラー詳細（任意）。
    """

    error_code: str
    error_message: str
    details: dict[str, Any] | None = None
