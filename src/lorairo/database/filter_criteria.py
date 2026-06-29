"""ImageFilterCriteria - データベースフィルタリング専用の条件クラス

このモジュールはデータベース層で使用される画像フィルタリング条件を定義します。
GUI/ServiceレイヤーのSearchConditionsとは分離され、DB操作の明確な契約を提供します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ImageFilterCriteria:
    """データベース層の画像フィルタリング条件

    DB Repository/Manager層で使用される画像検索条件を表すデータクラス。
    すべてのパラメータにデフォルト値を持ち、部分的な条件指定が可能です。

    Attributes:
        tags: 検索するタグのリスト
        caption: 検索するキャプション文字列
        excluded_tags: 除外するタグのリスト（NOT検索）
        resolution: 検索対象の解像度(長辺)、0の場合はオリジナル画像
        use_and: 複数タグ指定時の検索方法 (True: AND, False: OR)
        start_date: 検索開始日時 (ISO 8601形式)
        end_date: 検索終了日時 (ISO 8601形式)
        include_untagged: タグが付いていない画像のみを対象とするか
        include_nsfw: NSFWコンテンツを含む画像を除外しないか
        include_unrated: 未評価画像を含めるか (False: 手動またはAI評価のいずれか1つ以上を持つ画像のみ)
        only_unrated: rating が無い画像のみを対象とするか
        missing_model_litellm_id: 指定モデルのannotation行が無い画像のみを対象とするか
        manual_rating_filter: 指定した手動レーティングを持つ画像のみを対象とするか。
            単一値 (str) または複数値 (list[str]) を受け付ける。複数値は選択集合の
            OR (いずれかに一致) として扱う (Issue #811 マルチセレクト chip)。番兵
            "UNRATED" (手動レーティングなし) / "RATED" (手動レーティングあり) を
            通常値と併用した場合も同じ集合内 OR で合成する。
        ai_rating_filter: 指定したAI評価レーティングを持つ画像のみを対象とするか (多数決ロジック)。
            単一値 (str) または複数値 (list[str]) を受け付ける。複数値は選択集合の
            OR として扱い、多数決は「選択集合のいずれかに一致する評価」を母数に判定する。
        rating_combine: manual_rating_filter と ai_rating_filter の組合せ方。
            "and" (デフォルト, 両方を満たす) または "or" (いずれかを満たす)。両方が
            指定されたときのみ意味を持ち、片方のみ指定時は常に AND と等価。
        manual_edit_filter: アノテーションが手動編集されたかでフィルタするか
        score_min: 最小スコア値（0.0-10.0）
        score_max: 最大スコア値（0.0-10.0）
        project_name: フィルタ対象プロジェクト名（Phase C完了後に有効化）
        project_id: フィルタ対象プロジェクトID（Phase C完了後に高速路）
        limit: 取得件数上限。None の場合は無制限
        offset: 取得開始位置
        image_ids: 明示的な画像IDリスト。指定時は exact-set selector として扱い、
            他のフィルタ次元（tags / caption / include_nsfw / rating / score 等）を
            すべてバイパスして指定IDをそのまま対象にする（ADR 0055）。GUI が
            ステージング集合を criteria 経由でエクスポートする際に使用する。
            最大 ImageRepository.EXACT_SET_MAX_IDS 件（= ステージング上限 500）。
            超過時は ValueError（ADR 0056）。
        sort_field: ソートキー。"image_id"（デフォルト）または "file_path"。
        sort_direction: ソート方向。"asc"（デフォルト）または "desc"。
    """

    tags: list[str] | None = None
    caption: str | None = None
    excluded_tags: list[str] | None = None
    resolution: int = 0
    use_and: bool = True
    start_date: str | None = None
    end_date: str | None = None
    include_untagged: bool = False
    include_nsfw: bool = False
    include_unrated: bool = True
    only_unrated: bool = False
    missing_model_litellm_id: str | None = None
    manual_rating_filter: str | list[str] | None = None
    ai_rating_filter: str | list[str] | None = None
    # Issue #811: manual / AI レーティングフィルタの組合せ方 ("and" | "or")
    rating_combine: str = "and"
    manual_edit_filter: bool | None = None
    score_min: float | None = None
    score_max: float | None = None
    # Phase 4: Search サイドバー強化 facets
    reviewed_at_filter: str | None = None  # "unreviewed" | "reviewed" | None=全て
    error_state_filter: str | None = None  # "has_error" | "no_error" | None=全て
    model_filter: list[str] | None = None  # litellm_id リスト。None=全モデル
    # Phase C (projects テーブル追加) 完了後に DB フィルタを有効化
    project_name: str | None = None
    project_id: int | None = None
    limit: int | None = None
    offset: int = 0
    # Issue #965: 検索フェーズでアノテーション (tags/captions/scores/score_labels/
    # ratings) を先読みするか。False の場合は id + 各テーブルカラムのみ取得し、
    # アノテーションは選択 → プレビュー表示時に遅延取得する (検索→レビュー表示の高速化)。
    include_annotations: bool = True
    # ADR 0055: 指定時は他フィルタを bypass する exact-set selector
    image_ids: list[int] | None = None
    # Issue #697: images search で使用するソート条件
    sort_field: str = "image_id"  # "image_id" または "file_path"
    sort_direction: str = "asc"  # "asc" または "desc"

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> ImageFilterCriteria:
        """キーワード引数から ImageFilterCriteria を生成（後方互換性用）

        既存コードで `get_images_by_filter(**conditions)` のように
        辞書を展開して呼び出している箇所の互換性を維持します。

        Args:
            **kwargs: フィルター条件のキーワード引数

        Returns:
            ImageFilterCriteria: 生成されたフィルター条件オブジェクト

        Example:
            >>> criteria = ImageFilterCriteria.from_kwargs(
            ...     tags=["anime", "landscape"],
            ...     resolution=1024,
            ...     use_and=True
            ... )
        """
        # データクラスの全フィールド名を取得
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}

        # 有効なフィールドのみを抽出
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_fields}

        return cls(**filtered_kwargs)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（レガシーコードとの互換性用）

        Returns:
            dict[str, Any]: フィルター条件の辞書
        """
        return {
            "tags": self.tags,
            "caption": self.caption,
            "excluded_tags": self.excluded_tags,
            "resolution": self.resolution,
            "use_and": self.use_and,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "include_untagged": self.include_untagged,
            "include_nsfw": self.include_nsfw,
            "include_unrated": self.include_unrated,
            "only_unrated": self.only_unrated,
            "missing_model_litellm_id": self.missing_model_litellm_id,
            "manual_rating_filter": self.manual_rating_filter,
            "ai_rating_filter": self.ai_rating_filter,
            "rating_combine": self.rating_combine,
            "manual_edit_filter": self.manual_edit_filter,
            "score_min": self.score_min,
            "score_max": self.score_max,
            "reviewed_at_filter": self.reviewed_at_filter,
            "error_state_filter": self.error_state_filter,
            "model_filter": self.model_filter,
            "project_name": self.project_name,
            "project_id": self.project_id,
            "limit": self.limit,
            "offset": self.offset,
            "include_annotations": self.include_annotations,
            "image_ids": self.image_ids,
            "sort_field": self.sort_field,
            "sort_direction": self.sort_direction,
        }
