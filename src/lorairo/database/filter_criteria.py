"""ImageFilterCriteria - データベースフィルタリング専用の条件クラス

このモジュールはデータベース層で使用される画像フィルタリング条件を定義します。
GUI/ServiceレイヤーのSearchConditionsとは分離され、DB操作の明確な契約を提供します。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageFilterCriteria:
    """データベース層の画像フィルタリング条件

    DB Repository/Manager層で使用される画像検索条件を表すデータクラス。
    すべてのパラメータにデフォルト値を持ち、部分的な条件指定が可能です。

    Attributes:
        tags: 検索するタグのリスト
        caption: 検索するキャプション文字列
        resolution: 検索対象の解像度(長辺)、0の場合はオリジナル画像
        use_and: 複数タグ指定時の検索方法 (True: AND, False: OR)
        start_date: 検索開始日時 (ISO 8601形式)
        end_date: 検索終了日時 (ISO 8601形式)
        include_untagged: タグが付いていない画像のみを対象とするか
        include_nsfw: NSFWコンテンツを含む画像を除外しないか
        include_unrated: 未評価画像を含めるか (False: 手動またはAI評価のいずれか1つ以上を持つ画像のみ)
        manual_rating_filter: 指定した手動レーティングを持つ画像のみを対象とするか
        ai_rating_filter: 指定したAI評価レーティングを持つ画像のみを対象とするか (多数決ロジック)
        manual_edit_filter: アノテーションが手動編集されたかでフィルタするか
        score_min: 最小スコア値（0.0-10.0）
        score_max: 最大スコア値（0.0-10.0）
    """

    tags: list[str] | None = None
    caption: str | None = None
    resolution: int = 0
    use_and: bool = True
    start_date: str | None = None
    end_date: str | None = None
    include_untagged: bool = False
    include_nsfw: bool = False
    include_unrated: bool = True
    manual_rating_filter: str | None = None
    ai_rating_filter: str | None = None
    manual_edit_filter: bool | None = None
    score_min: float | None = None
    score_max: float | None = None

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
            "resolution": self.resolution,
            "use_and": self.use_and,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "include_untagged": self.include_untagged,
            "include_nsfw": self.include_nsfw,
            "include_unrated": self.include_unrated,
            "manual_rating_filter": self.manual_rating_filter,
            "ai_rating_filter": self.ai_rating_filter,
            "manual_edit_filter": self.manual_edit_filter,
            "score_min": self.score_min,
            "score_max": self.score_max,
        }
