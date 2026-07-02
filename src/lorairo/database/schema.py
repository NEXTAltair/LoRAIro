"""lorairo 画像データベースの SQLAlchemy スキーマ定義"""

from __future__ import annotations  # 関係のフォワードリファレンス

import datetime
from typing import NotRequired, TypedDict

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,  # Table で使用
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,  # 中間テーブル定義で使用
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ADR 0023 Phase 1.11 (Issue #238): MANUAL_EDIT 行は推論経路に乗らない特殊行のため、
# `litellm_model_id` UNIQUE NOT NULL 制約を満たす sentinel 値を予約する。
# `provider/<model>` 形式と衝突しないよう先頭/末尾を `__` で囲んだ非 LiteLLM ID にする。
MANUAL_EDIT_NAME = "MANUAL_EDIT"
MANUAL_EDIT_PROVIDER = "user"
MANUAL_EDIT_LITELLM_ID = "__manual_edit__"

# タグ/キャプションの soft-reject 種別 (reject_reason 列の値、Issue #1003 / ADR 0065)。
# rejected_at が非 NULL のときのみ意味を持つ。NULL = 採用中。
# エクスポート抽出は従来どおり ``rejected_at IS NULL`` で行い、3値すべて除外される
# (reject_reason は表示復元と記録上の意味のためだけに使う)。
REJECT_REASON_NOT_NEEDED = "not_needed"  # 無効化: 正しいが今回不要。打ち消し線で残す。
REJECT_REASON_INCORRECT = "incorrect"  # 除外: 間違い。✕・非表示。
REJECT_REASON_REPLACED = "replaced"  # 置換により別タグへ移行して不要。非表示。


# --- Base Class ---
class Base(DeclarativeBase):
    """SQLAlchemy モデルの基底クラス"""

    # 全てのテーブルに適用される可能性のある共通設定 (例: 型アノテーションマップ)
    # type_annotation_map = {
    #     datetime.datetime: TIMESTAMP(timezone=True),
    # }
    pass


# --- Models ---


# 中間テーブル (モデルと機能タイプの多対多関連)
model_function_associations = Table(
    "model_function_associations",
    Base.metadata,
    Column("model_id", Integer, ForeignKey("models.id"), primary_key=True),
    Column("type_id", Integer, ForeignKey("model_types.id"), primary_key=True),
)


class ModelType(Base):
    """モデルの機能タイプ ('caption', 'tag', 'score', 'multimodal', 'upscaler' など)"""

    __tablename__ = "model_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Relationship (Modelへの逆参照、必要であれば)
    # models: Mapped[list["Model"]] = relationship(
    #     "Model",
    #     secondary=model_function_associations,
    #     back_populates="model_types"
    # )

    def __repr__(self) -> str:
        return f"<ModelType(id={self.id}, name='{self.name}')>"


class Model(Base):
    """AI モデル情報を格納するテーブル"""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ADR 0023 Phase 1.11 (Issue #238): 役割分担を以下に再構成
    #   name: 表示名 (非 UNIQUE) — 例 "gpt-4.1"
    #   provider: ルーティング元 (非 UNIQUE) — 例 "openrouter" / "openai"
    #   litellm_model_id: ルーティングキー (UNIQUE NOT NULL) — 例 "openrouter/openai/gpt-4.1"
    name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str | None] = mapped_column(String)
    discontinued_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Model metadata fields for annotation processing integration
    litellm_model_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    estimated_size_gb: Mapped[float | None] = mapped_column(Float)
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    # 多対多: Model <-> ModelType
    model_types: Mapped[list[ModelType]] = relationship(
        "ModelType",
        secondary=model_function_associations,
        # back_populates="models"  # ModelType側に models リレーションを定義する場合
        lazy="selectin",  # N+1問題を避けるために Eager Loading を推奨
    )

    # 一対多: Model -> Annotations
    tags: Mapped[list[Tag]] = relationship("Tag", back_populates="model")
    captions: Mapped[list[Caption]] = relationship("Caption", back_populates="model")
    scores: Mapped[list[Score]] = relationship("Score", back_populates="model")
    score_labels: Mapped[list[ScoreLabel]] = relationship("ScoreLabel", back_populates="model")
    ratings: Mapped[list[Rating]] = relationship("Rating", back_populates="model")
    provider_batch_jobs: Mapped[list[ProviderBatchJob]] = relationship(
        "ProviderBatchJob", back_populates="model"
    )
    provider_batch_items: Mapped[list[ProviderBatchItem]] = relationship(
        "ProviderBatchItem", back_populates="model"
    )

    def __repr__(self) -> str:
        return f"<Model(id={self.id}, name='{self.name}')>"

    # UI用プロパティ（ModelInfo代替機能）
    @property
    def is_recommended(self) -> bool:
        """推奨モデル判定（UIロジック）"""
        if not self.name:
            return False

        name_lower = self.name.lower()

        # 高品質Caption生成モデル
        caption_recommended = ["gpt-4o", "claude-3-5-sonnet", "claude-3-sonnet", "gemini-pro"]

        # 高精度タグ生成モデル
        tags_recommended = ["wd-v1-4", "wd-tagger", "deepdanbooru", "wd-swinv2"]

        # 品質評価モデル
        scores_recommended = ["clip-aesthetic", "musiq", "aesthetic-scorer"]

        all_recommended = caption_recommended + tags_recommended + scores_recommended

        return any(rec in name_lower for rec in all_recommended)

    @property
    def available(self) -> bool:
        """利用可能性判定"""
        return self.discontinued_at is None

    @property
    def capabilities(self) -> list[str]:
        """モデルの機能名リストを ``model_types`` リレーションから導出して返す。

        annotator_adapter / model_selection_widget / model_checkbox_widget など
        複数サービスから現役で参照される機能プロパティ。
        """
        return [model_type.name for model_type in self.model_types]


class Project(Base):
    """プロジェクト情報を格納するテーブル"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    images: Mapped[list[Image]] = relationship("Image", back_populates="project")

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}')>"


class Image(Base):
    """オリジナル画像情報を格納するテーブル"""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    phash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    original_image_path: Mapped[str] = mapped_column(String, nullable=False)
    stored_image_path: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str | None] = mapped_column(String)
    has_alpha: Mapped[bool | None] = mapped_column(Boolean)
    filename: Mapped[str | None] = mapped_column(String)
    extension: Mapped[str] = mapped_column(String, nullable=False)
    color_space: Mapped[str | None] = mapped_column(String)
    icc_profile: Mapped[str | None] = mapped_column(String)
    # グレースケール相当判定 (Issue #631 / ADR 0061): 内容ベースでカラー画像とグレー画像を
    # 区別する。既存 DB の行は NULL のまま (遅延 backfill 方針)。
    is_grayscale_like: Mapped[bool | None] = mapped_column(Boolean)
    colorfulness_score: Mapped[float | None] = mapped_column(Float)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # アノテーション品質レビュー完了タイムスタンプ (Wireframes v11 Frame 5 · Results)。
    # NULL = 未レビュー、値あり = accept 済み (確認完了)。rejected_at (タグ単位) と対称。
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped[Project | None] = relationship("Project", back_populates="images")
    processed_images: Mapped[list[ProcessedImage]] = relationship(
        "ProcessedImage", back_populates="image", cascade="all, delete-orphan"
    )
    tags: Mapped[list[Tag]] = relationship("Tag", back_populates="image", cascade="all, delete-orphan")
    captions: Mapped[list[Caption]] = relationship(
        "Caption", back_populates="image", cascade="all, delete-orphan"
    )
    scores: Mapped[list[Score]] = relationship(
        "Score", back_populates="image", cascade="all, delete-orphan"
    )
    score_labels: Mapped[list[ScoreLabel]] = relationship(
        "ScoreLabel", back_populates="image", cascade="all, delete-orphan"
    )
    ratings: Mapped[list[Rating]] = relationship(
        "Rating", back_populates="image", cascade="all, delete-orphan"
    )
    error_records: Mapped[list[ErrorRecord]] = relationship(
        "ErrorRecord", back_populates="image", cascade="all, delete-orphan"
    )
    provider_batch_items: Mapped[list[ProviderBatchItem]] = relationship(
        "ProviderBatchItem", back_populates="image"
    )

    # uuid と phash の組み合わせはユニークであるべき
    # phash が NOT NULL になったため、複合ユニーク制約を追加可能
    __table_args__ = (UniqueConstraint("uuid", "phash", name="uix_uuid_phash"),)

    def __repr__(self) -> str:
        return f"<Image(id={self.id}, uuid='{self.uuid}', filename='{self.filename}')>"


class ProcessedImage(Base):
    """処理済み画像 (リサイズ等) 情報を格納するテーブル"""

    __tablename__ = "processed_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stored_image_path: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str | None] = mapped_column(String)
    has_alpha: Mapped[bool] = mapped_column(Boolean, nullable=False)  # 処理後は明確なはず
    filename: Mapped[str | None] = mapped_column(String)
    color_space: Mapped[str | None] = mapped_column(String)
    icc_profile: Mapped[str | None] = mapped_column(String)
    upscaler_used: Mapped[str | None] = mapped_column(String)  # 使用されたアップスケーラー名
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    image: Mapped[Image] = relationship("Image", back_populates="processed_images")

    __table_args__ = (
        UniqueConstraint("image_id", "width", "height", "filename", name="uix_proc_img_dims_name"),
    )

    def __repr__(self) -> str:
        return f"<ProcessedImage(id={self.id}, image_id={self.image_id}, width={self.width}, height={self.height})>"


class Tag(Base):
    """画像に関連付けられたタグ情報"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # tag_id は genai-tag-db-tools の内の ID を参照するが、
    # 外部 DB のため ForeignKey 制約は設定しない。NULL も許容。
    tag_id: Mapped[int | None] = mapped_column(Integer)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    tag: Mapped[str] = mapped_column(String, nullable=False)
    # existing: 元ファイル(プロンプト等)由来のタグかどうかを示すフラグ (AI生成ではない)
    existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_edited_manually: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    rejected_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # なぜ soft-reject したか (Issue #1003)。rejected_at が非 NULL のときのみ意味を持つ。
    # NULL=採用 / 'not_needed'=無効化 / 'incorrect'=除外 / 'replaced'=置換移行。
    reject_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped[Image] = relationship("Image", back_populates="tags")
    model: Mapped[Model] = relationship("Model", back_populates="tags")

    __table_args__ = (
        Index("ix_tags_image_id", "image_id"),
        Index("ix_tags_tag", "tag"),
        Index("ix_tags_rejected_at", "rejected_at"),
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, image_id={self.image_id}, tag='{self.tag}')>"


class RefinementIgnore(Base):
    """タグ refinement リコメンドのローカル無視設定 (#931)。

    特定タグ (`tag`) の特定理由 (`reason_code`) のリコメンドを抑制する。
    1タグに複数 reason が付くため tag + reason_code 単位で無視できる。
    画像には紐づかない (タグ語彙単位)。
    """

    __tablename__ = "refinement_ignores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    # genai-tag-db-tools の RefinementReason.code (Literal 23種) の文字列値
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tag", "reason_code", name="uix_refinement_ignore_tag_reason"),
        Index("ix_refinement_ignores_tag", "tag"),
    )

    def __repr__(self) -> str:
        return f"<RefinementIgnore(tag='{self.tag}', reason_code='{self.reason_code}')>"


class Caption(Base):
    """画像に関連付けられたキャプション情報"""

    __tablename__ = "captions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    caption: Mapped[str] = mapped_column(String, nullable=False)
    # existing: 元ファイル由来のキャプションかどうかを示すフラグ
    existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_edited_manually: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejected_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # なぜ soft-reject したか (Issue #1003)。tags と対称。既定 'incorrect' (UI 未実装)。
    reject_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped[Image] = relationship("Image", back_populates="captions")
    model: Mapped[Model] = relationship("Model", back_populates="captions")

    __table_args__ = (
        Index("ix_captions_image_id", "image_id"),
        Index("ix_captions_rejected_at", "rejected_at"),
    )

    def __repr__(self) -> str:
        return f"<Caption(id={self.id}, image_id={self.image_id}, caption='{self.caption[:20]}...')>"


class Score(Base):
    """画像に関連付けられたスコア情報"""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    display_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_edited_manually: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped[Image] = relationship("Image", back_populates="scores")
    model: Mapped[Model] = relationship("Model", back_populates="scores")

    __table_args__ = (Index("ix_scores_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<Score(id={self.id}, image_id={self.image_id}, score={self.score})>"


class ScoreLabel(Base):
    """canonical scorer による categorical 分類ラベル (ADR 0027 / iam-lib ADR 0002)。

    aesthetic_shadow_v1/v2 や cafe_aesthetic 等、配布元が canonical な分類ラベルを
    提供する scorer モデルの出力 (例: ``"very aesthetic"`` / ``"aesthetic"``) を、
    数値 ``Score`` とは独立に保持する。``tags`` テーブルは content tag (WDTagger 等)
    専用に純化され、scorer 由来の categorical label は本テーブルで扱う。

    AestheticShadow が ``scores={"hq": x, "lq": 1-x}`` で 2 行の Score を返す一方、
    score_label は 1 image × 1 model に 1 行のみ。
    """

    __tablename__ = "score_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    is_edited_manually: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped[Image] = relationship("Image", back_populates="score_labels")
    model: Mapped[Model] = relationship("Model", back_populates="score_labels")

    __table_args__ = (Index("ix_score_labels_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<ScoreLabel(id={self.id}, image_id={self.image_id}, label='{self.label}')>"


class Rating(Base):
    """AI モデルによるレーティング結果"""

    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Rating は必ず Image と Model に紐づく想定 (NULL 不許可)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,  # モデル削除時 Rating も削除
    )
    raw_rating_value: Mapped[str] = mapped_column(String)  # モデルが出力した生の値
    normalized_rating: Mapped[str] = mapped_column(String)  # Civitai 基準 ('PG', 'PG-13', 'R', 'X', 'XXX')
    confidence_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped[Image] = relationship("Image", back_populates="ratings")
    model: Mapped[Model] = relationship("Model", back_populates="ratings")

    __table_args__ = (
        Index("ix_ratings_image_id", "image_id"),
        # AI レーティングフィルタ (model_id IN (...) + GROUP BY image_id) を index seek 化する
        Index("ix_ratings_model_id_image_id", "model_id", "image_id"),
    )

    def __repr__(self) -> str:
        return f"<Rating(id={self.id}, image_id={self.image_id}, rating='{self.normalized_rating}')>"


class ErrorRecord(Base):
    """処理エラー記録テーブル"""

    __tablename__ = "error_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # エラー発生コンテキスト
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=True)
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'registration', 'annotation', 'processing', 'search', 'thumbnail'

    # エラー詳細
    error_type: Mapped[str] = mapped_column(String, nullable=False)
    # 'pHash calculation', 'DB constraint', 'File I/O', 'API error', 'Network', etc.
    error_message: Mapped[str] = mapped_column(String, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(String)

    # 追加コンテキスト
    file_path: Mapped[str | None] = mapped_column(String)
    model_name: Mapped[str | None] = mapped_column(String)

    # 手動「解決済みマーク」管理 (Error Log Viewer / Detail Dialog で利用)
    # ADR 0033 Decision 8: retry_count は drop 済み (LoRAIro 側で自動 retry はしない)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # タイムスタンプ
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    # Relationships
    image: Mapped[Image | None] = relationship("Image", back_populates="error_records")

    # Indexes
    __table_args__ = (
        Index("ix_error_records_operation_type", "operation_type"),
        Index("ix_error_records_created_at", "created_at"),
        Index("ix_error_records_resolved", "resolved_at"),
    )

    def __repr__(self) -> str:
        return f"<ErrorRecord(id={self.id}, operation='{self.operation_type}', type='{self.error_type}')>"


class ImageFilenameAlias(Base):
    """重複スキップされた画像のファイル名エイリアス。

    pHash重複で登録スキップされた画像のファイル名stemと、
    重複元のimage_idを記録する。バッチインポート時のマッチングに使用。
    """

    __tablename__ = "image_filename_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    stem: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    image: Mapped[Image] = relationship("Image")

    __table_args__ = (
        Index("ix_image_filename_aliases_stem", "stem"),
        UniqueConstraint("stem", name="uix_alias_stem"),
    )

    def __repr__(self) -> str:
        return f"<ImageFilenameAlias(id={self.id}, stem='{self.stem}', image_id={self.image_id})>"


class ProviderBatchJob(Base):
    """プロバイダ Batch API の永続 job 状態。"""

    __tablename__ = "provider_batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String)
    endpoint: Mapped[str | None] = mapped_column(String)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    canceled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    canceled_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    imported_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    input_artifact_path: Mapped[str | None] = mapped_column(String)
    output_artifact_path: Mapped[str | None] = mapped_column(String)
    error_artifact_path: Mapped[str | None] = mapped_column(String)
    raw_provider_payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    model: Mapped[Model | None] = relationship("Model", back_populates="provider_batch_jobs")
    items: Mapped[list[ProviderBatchItem]] = relationship(
        "ProviderBatchItem", back_populates="job", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[ProviderBatchArtifact]] = relationship(
        "ProviderBatchArtifact", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_provider_batch_jobs_provider", "provider"),
        Index("ix_provider_batch_jobs_status", "status"),
        Index("ix_provider_batch_jobs_created_at", "created_at"),
        Index(
            "uq_provider_batch_jobs_provider_job",
            "provider",
            "provider_job_id",
            unique=True,
            sqlite_where=provider_job_id.is_not(None),
        ),
    )

    def __repr__(self) -> str:
        return f"<ProviderBatchJob(id={self.id}, provider='{self.provider}', status='{self.status}')>"


class ProviderBatchItem(Base):
    """Provider Batch API job 内の request/result item。"""

    __tablename__ = "provider_batch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("provider_batch_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    custom_id: Mapped[str] = mapped_column(String, nullable=False)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(String)
    raw_request: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[ProviderBatchJob] = relationship("ProviderBatchJob", back_populates="items")
    image: Mapped[Image | None] = relationship("Image", back_populates="provider_batch_items")
    model: Mapped[Model | None] = relationship("Model", back_populates="provider_batch_items")

    __table_args__ = (
        UniqueConstraint("job_id", "custom_id", name="uix_provider_batch_items_job_custom_id"),
        Index("ix_provider_batch_items_status", "status"),
        Index("ix_provider_batch_items_image_id", "image_id"),
        Index("ix_provider_batch_items_model_id", "model_id"),
    )

    def __repr__(self) -> str:
        return f"<ProviderBatchItem(id={self.id}, job_id={self.job_id}, custom_id='{self.custom_id}')>"


class ProviderBatchArtifact(Base):
    """Provider Batch API job に紐づく local/provider artifact。"""

    __tablename__ = "provider_batch_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("provider_batch_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    local_path: Mapped[str] = mapped_column(String, nullable=False)
    provider_file_id: Mapped[str | None] = mapped_column(String)
    sha256: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    job: Mapped[ProviderBatchJob] = relationship("ProviderBatchJob", back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "artifact_type",
            "local_path",
            name="uix_provider_batch_artifacts_job_type_path",
        ),
        Index("ix_provider_batch_artifacts_type", "artifact_type"),
    )

    def __repr__(self) -> str:
        return f"<ProviderBatchArtifact(id={self.id}, job_id={self.job_id}, type='{self.artifact_type}')>"


# --- TypedDicts for data transfer ---


class ImageDict(TypedDict):
    id: NotRequired[int]  # DBから取得時にのみ存在
    uuid: str
    phash: str  # NOT NULL制約（DB登録時に必須計算）
    original_image_path: str
    stored_image_path: str
    width: int
    height: int
    format: str
    mode: str | None
    has_alpha: bool | None
    filename: str | None
    extension: str
    color_space: str | None
    icc_profile: str | None
    created_at: NotRequired[datetime.datetime]  # DBから取得時にのみ存在
    updated_at: NotRequired[datetime.datetime]  # DBから取得時にのみ存在


class ProcessedImageDict(TypedDict):
    id: NotRequired[int]
    image_id: int  # Must be provided when adding
    stored_image_path: str
    width: int
    height: int
    mode: str | None
    has_alpha: bool
    filename: str | None
    color_space: str | None
    icc_profile: str | None
    upscaler_used: NotRequired[str | None]  # 使用されたアップスケーラー名
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class TagAnnotationData(TypedDict):
    id: NotRequired[int]
    tag_id: int | None
    image_id: NotRequired[int | None]  # Set by save_annotations
    model_id: int | None
    tag: str
    existing: bool
    is_edited_manually: bool | None
    confidence_score: float | None
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class CaptionAnnotationData(TypedDict):
    id: NotRequired[int]
    image_id: NotRequired[int | None]  # Set by save_annotations
    model_id: int | None
    caption: str
    existing: bool
    is_edited_manually: bool | None
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class ScoreAnnotationData(TypedDict):
    id: NotRequired[int]
    image_id: NotRequired[int | None]  # Set by save_annotations
    model_id: int | None
    score: float
    display_score: NotRequired[float | None]
    # is_edited_manually: bool # Default False, NOT NULL in schema (check migration)
    is_edited_manually: bool | None  # nullable=True に合わせた
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class ScoreLabelAnnotationData(TypedDict):
    """canonical scorer の score_labels 永続化用 TypedDict (ADR 0027)。"""

    id: NotRequired[int]
    image_id: NotRequired[int]  # Set by save_annotations
    model_id: int  # Must be provided
    label: str
    is_edited_manually: bool | None
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class RatingAnnotationData(TypedDict):
    id: NotRequired[int]
    image_id: NotRequired[int]  # Set by save_annotations
    model_id: int  # Must be provided
    raw_rating_value: str
    normalized_rating: str
    confidence_score: float | None
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class AnnotationsDict(TypedDict):
    tags: NotRequired[list[TagAnnotationData]]
    captions: NotRequired[list[CaptionAnnotationData]]
    scores: NotRequired[list[ScoreAnnotationData]]
    score_labels: NotRequired[list[ScoreLabelAnnotationData]]
    ratings: NotRequired[list[RatingAnnotationData]]


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
    resolved_at: NotRequired[datetime.datetime | None]
    created_at: NotRequired[datetime.datetime]


class ProviderBatchJobData(TypedDict):
    id: NotRequired[int]
    provider: str
    provider_job_id: NotRequired[str | None]
    status: str
    provider_status: NotRequired[str | None]
    endpoint: NotRequired[str | None]
    model_id: NotRequired[int | None]
    request_count: NotRequired[int]
    succeeded_count: NotRequired[int]
    failed_count: NotRequired[int]
    canceled_count: NotRequired[int]
    expired_count: NotRequired[int]
    submitted_at: NotRequired[datetime.datetime | None]
    completed_at: NotRequired[datetime.datetime | None]
    canceled_at: NotRequired[datetime.datetime | None]
    imported_at: NotRequired[datetime.datetime | None]
    expires_at: NotRequired[datetime.datetime | None]
    input_artifact_path: NotRequired[str | None]
    output_artifact_path: NotRequired[str | None]
    error_artifact_path: NotRequired[str | None]
    raw_provider_payload: NotRequired[str | None]
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class ProviderBatchItemData(TypedDict):
    id: NotRequired[int]
    job_id: int
    custom_id: str
    image_id: NotRequired[int | None]
    model_id: NotRequired[int | None]
    task_type: str
    status: str
    error_type: NotRequired[str | None]
    error_message: NotRequired[str | None]
    raw_request: NotRequired[str | None]
    raw_response: NotRequired[str | None]
    created_at: NotRequired[datetime.datetime]
    updated_at: NotRequired[datetime.datetime]


class ProviderBatchArtifactData(TypedDict):
    id: NotRequired[int]
    job_id: int
    artifact_type: str
    local_path: str
    provider_file_id: NotRequired[str | None]
    sha256: NotRequired[str | None]
    created_at: NotRequired[datetime.datetime]
