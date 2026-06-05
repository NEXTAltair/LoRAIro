"""JSONL custom_id → DB image_id の一括照合サービス。

OpenAI Batch APIのcustom_idフィールドからマッチングキーを抽出し、
DBに登録済みの画像とマッチングする。

custom_id には 2 系統がある:

- ADR 0062 形式 ``ph:{phash}:le:{long_edge}`` (LoRAIro が生成する Provider Batch 投入)。
  pHash で照合する (長辺解像度はキーの一意化用で、照合は完全一致 pHash ベース)。
- ファイル名 stem 形式 (外部生成 JSONL 等の旧来フォーマット)。
"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from lorairo.database.repository.image import ImageRepository
from lorairo.services.provider_batch_service import ProviderBatchJobService


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

        ADR 0062 形式 (``ph:{phash}:le:{long_edge}``) は pHash で、それ以外は
        ファイル名 stem で照合する。

        Args:
            custom_ids: OpenAI Batch APIのcustom_idリスト。

        Returns:
            マッチング結果。
        """
        # custom_id を pHash 形式と stem 形式に振り分ける
        phash_le_by_custom_id: dict[str, tuple[str, int]] = {}
        stem_custom_ids: list[str] = []
        for custom_id in custom_ids:
            parsed = ProviderBatchJobService.parse_custom_id(custom_id)
            if parsed is not None:
                phash_le_by_custom_id[custom_id] = parsed
            else:
                stem_custom_ids.append(custom_id)

        matched: dict[str, int] = {}
        unmatched: list[str] = []
        ambiguous: dict[str, list[int]] = {}

        # ADR 0062: (pHash, 長辺解像度) の複合キーで突合する。同一 pHash で長辺の異なる
        # レコードが DB に共存しても、custom_id の長辺に一致する行へ正しくマッチする。
        if phash_le_by_custom_id:
            phashes = {phash for phash, _ in phash_le_by_custom_id.values()}
            phash_le_to_ids = self._repository.find_image_ids_by_phash_long_edge(phashes)
            for custom_id, key in phash_le_by_custom_id.items():
                image_ids = phash_le_to_ids.get(key)
                if image_ids:
                    # 代表 (昇順先頭) を matched に、同一素材の重複登録は ambiguous に残す
                    # (legacy JSONL import は代表のみ保存。submit/import 経路は raw_request の
                    # 対応表で全 image へ fan-out する)。
                    matched[custom_id] = image_ids[0]
                    if len(image_ids) > 1:
                        ambiguous[custom_id] = list(image_ids)
                else:
                    unmatched.append(custom_id)

        # 旧来フォーマット: ファイル名 stem で照合
        if stem_custom_ids:
            filename_index = self._repository.get_all_image_filename_index()
            for custom_id in stem_custom_ids:
                stem = self.extract_stem(custom_id)
                image_id = filename_index.get(stem)
                if image_id is not None:
                    matched[custom_id] = image_id
                else:
                    unmatched.append(custom_id)

        return ImageMatchResult(matched=matched, unmatched=unmatched, ambiguous=ambiguous)

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
