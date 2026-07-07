# src/lorairo/gui/workers/translation_candidates_worker.py
"""翻訳管理ダイアログの候補訳を非同期解決する worker (#1232)。

`TranslationAddDialog` はコンストラクタと言語切替のたびに
`service.list_translation_candidates(canonical, language)` を同期呼び出ししており、
tag DB (SQLite) のクエリが warm でも約 1 秒 (cold で最大 5 秒超) メインスレッドを
ブロックしてポップアップ表示が固まっていた (#1232)。クエリ自体は #1209 で index 化済みで、
原因は「GUI スレッド上の同期実行」。本 worker は候補取得を background へ退避し、
結果を Signal で返す。
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from ...utils.log import logger
from .base import LoRAIroWorkerBase

# canonical, language を渡すと (候補訳リスト, 現在の主訳) を返す取得関数の型。
# 実体は TagManagementService.list_translation_candidates。
CandidatesFn = Callable[[str, str], "tuple[list[str], str | None]"]


@dataclass
class TranslationCandidatesResult:
    """候補訳の解決結果。

    Attributes:
        canonical: 解決対象の canonical タグ (受信側の照合用)。
        language: 解決対象の言語コード ("ja" / "en")。
        generation: 起動時の世代番号 (言語切替でも古い結果を弾く)。
        candidates: 候補訳リスト (順序保持・重複排除済み)。
        preferred: 現在の主訳 (無ければ None)。
    """

    canonical: str
    language: str
    generation: int
    candidates: list[str]
    preferred: str | None


class TranslationCandidatesWorker(LoRAIroWorkerBase[TranslationCandidatesResult]):
    """canonical タグの指定言語の候補訳を非同期解決するワーカー (#1232)。"""

    _OPERATION_TYPE = "translation_candidates"

    def __init__(
        self,
        candidates_fn: CandidatesFn,
        canonical: str,
        language: str,
        generation: int = 0,
    ) -> None:
        """TranslationCandidatesWorker を初期化する。

        Args:
            candidates_fn: ``(canonical, language)`` で ``(候補訳, 主訳)`` を返す取得関数。
                通常は ``TagManagementService.list_translation_candidates``。
            canonical: 候補を列挙する canonical タグ文字列。
            language: 言語コード ("ja" / "en")。
            generation: 起動世代 (受信側のレース照合用)。
        """
        super().__init__()
        self._candidates_fn = candidates_fn
        self._canonical = canonical
        self._language = language
        self._generation = generation

    def execute(self) -> TranslationCandidatesResult:
        """候補取得関数を background で実行し結果を返す。

        取得失敗は空側へ縮退させ (ダイアログを開けなくしない)、空候補・主訳 None を返す。
        """
        candidates: list[str] = []
        preferred: str | None = None
        try:
            candidates, preferred = self._candidates_fn(self._canonical, self._language)
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            logger.warning(
                f"翻訳候補の非同期取得に失敗 (候補なし): canonical='{self._canonical}', "
                f"language='{self._language}': {e}"
            )
        logger.debug(
            f"translation candidates worker 完了: canonical='{self._canonical}', "
            f"language='{self._language}', gen={self._generation}, candidates={len(candidates)}"
        )
        return TranslationCandidatesResult(
            canonical=self._canonical,
            language=self._language,
            generation=self._generation,
            candidates=candidates,
            preferred=preferred,
        )
