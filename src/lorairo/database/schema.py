"""lorairo 画像データベースの SQLAlchemy スキーマ定義"""

from __future__ import annotations  # 関係のフォワードリファレンス

import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# --- Base Class ---
class Base(DeclarativeBase):
    """SQLAlchemy モデルの基底クラス"""

    # 全てのテーブルに適用される可能性のある共通設定 (例: 型アノテーションマップ)
    # type_annotation_map = {
    #     datetime.datetime: TIMESTAMP(timezone=True),
    # }
    pass


# --- Models ---


class Model(Base):
    """AI モデル情報を格納するテーブル"""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # 例: "vision", "score", "upscaler"
    provider: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tags: Mapped[list["Tag"]] = relationship("Tag", back_populates="model")
    captions: Mapped[list["Caption"]] = relationship("Caption", back_populates="model")
    scores: Mapped[list["Score"]] = relationship("Score", back_populates="model")
    ratings: Mapped[list["Rating"]] = relationship("Rating", back_populates="model")

    def __repr__(self) -> str:
        return f"<Model(id={self.id}, name='{self.name}', type='{self.type}')>"


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
    manual_rating: Mapped[str | None] = mapped_column(String)  # 手動評価 (Civitai基準)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    processed_images: Mapped[list["ProcessedImage"]] = relationship(
        "ProcessedImage", back_populates="image", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship("Tag", back_populates="image", cascade="all, delete-orphan")
    captions: Mapped[list["Caption"]] = relationship(
        "Caption", back_populates="image", cascade="all, delete-orphan"
    )
    scores: Mapped[list["Score"]] = relationship(
        "Score", back_populates="image", cascade="all, delete-orphan"
    )
    ratings: Mapped[list["Rating"]] = relationship(
        "Rating", back_populates="image", cascade="all, delete-orphan"
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
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    image: Mapped["Image"] = relationship("Image", back_populates="processed_images")

    __table_args__ = (
        UniqueConstraint("image_id", "width", "height", "filename", name="uix_proc_img_dims_name"),
    )

    def __repr__(self) -> str:
        return f"<ProcessedImage(id={self.id}, image_id={self.image_id}, width={self.width}, height={self.height})>"


class Tag(Base):
    """画像に関連付けられたタグ情報"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # tag_id は genai-tag-db-tools の tags_v4.db 内の ID を参照するが、
    # 外部 DB のため ForeignKey 制約は設定しない。NULL も許容。
    tag_id: Mapped[int | None] = mapped_column(Integer)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    tag: Mapped[str] = mapped_column(String, nullable=False)
    # existing: 元ファイル(プロンプト等)由来のタグかどうかを示すフラグ (AI生成ではない)
    existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_edited_manually: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped["Image"] = relationship("Image", back_populates="tags")
    model: Mapped["Model"] = relationship("Model", back_populates="tags")

    __table_args__ = (Index("ix_tags_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, image_id={self.image_id}, tag='{self.tag}')>"


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
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped["Image"] = relationship("Image", back_populates="captions")
    model: Mapped["Model"] = relationship("Model", back_populates="captions")

    __table_args__ = (Index("ix_captions_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<Caption(id={self.id}, image_id={self.image_id}, caption='{self.caption[:20]}...')>"


class Score(Base):
    """画像に関連付けられたスコア情報"""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    is_edited_manually: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    image: Mapped["Image"] = relationship("Image", back_populates="scores")
    model: Mapped["Model"] = relationship("Model", back_populates="scores")

    __table_args__ = (Index("ix_scores_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<Score(id={self.id}, image_id={self.image_id}, score={self.score})>"


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
    image: Mapped["Image"] = relationship("Image", back_populates="ratings")
    model: Mapped["Model"] = relationship("Model", back_populates="ratings")

    __table_args__ = (Index("ix_ratings_image_id", "image_id"),)

    def __repr__(self) -> str:
        return f"<Rating(id={self.id}, image_id={self.image_id}, model_id={self.model_id}, rating='{self.normalized_rating}')>"
