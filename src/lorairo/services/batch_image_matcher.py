"""JSONL custom_id → DB image_id の一括照合サービス。

OpenAI Batch APIのcustom_idフィールドからファイル名stemを抽出し、
DBに登録済みの画像とマッチングする。
"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from lorairo.database.db_repository import ImageRepository


@dataclass(frozen=True)
class ImageMatchResult:
    """画像マッチング結果。

    Attributes:
        matched: custom_id → image_id のマッピング。
        unmatched: マッチ失敗のcustom_idリスト。
        ambiguous: 複数候補があるcustom_id → image_idリスト（将来拡張用）。
    """

    matched: dict[str, int] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    ambiguous: dict[str, list[int]] = field(default_factory=dict)


class BatchImageMatcher:
    """custom_id → image_id の一括照合を行うサービス。"""

    def __init__(self, repository: ImageRepository) -> None:
        self._repository = repository

    def match_all(self, custom_ids: list[str]) -> ImageMatchResult:
        """全custom_idを一括照合する。

        Args:
            custom_ids: OpenAI Batch APIのcustom_idリスト。

        Returns:
            マッチング結果。
        """
        # DB全画像の filename stem → image_id インデックスを1クエリで構築
        filename_index = self._repository.get_all_image_filename_index()

        matched: dict[str, int] = {}
        unmatched: list[str] = []

        for custom_id in custom_ids:
            stem = self.extract_stem(custom_id)
            image_id = filename_index.get(stem)
            if image_id is not None:
                matched[custom_id] = image_id
            else:
                unmatched.append(custom_id)

        return ImageMatchResult(matched=matched, unmatched=unmatched)

    @staticmethod
    def extract_stem(custom_id: str) -> str:
        """custom_idからマッチング用stemを抽出する。

        Windows/Unixパス両対応。拡張子があれば除去する。

        Args:
            custom_id: OpenAI Batch APIのcustom_id。
                例: "H:\\lora\\images\\0262_1227"
                例: "/data/images/0262_1227.jpg"

        Returns:
            ファイル名stem部分。例: "0262_1227"
        """
        # Windows バックスラッシュ → スラッシュに正規化
        normalized = custom_id.replace("\\", "/")
        # PurePosixPathでstem抽出
        stem = PurePosixPath(normalized).stem
        # stemが空の場合（末尾スラッシュ等）はフォールバック
        if not stem:
            parts = normalized.rstrip("/").rsplit("/", 1)
            return parts[-1] if parts[-1] else custom_id
        return stem
