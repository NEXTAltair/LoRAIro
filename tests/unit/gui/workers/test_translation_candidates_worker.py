"""TranslationCandidatesWorker (#1232) のユニットテスト。

翻訳管理ポップアップの候補取得を GUI スレッド外へ退避する worker。取得関数を
background で実行し、失敗時は空候補へ縮退する。
"""

import pytest

from lorairo.gui.workers.translation_candidates_worker import (
    TranslationCandidatesResult,
    TranslationCandidatesWorker,
)

pytestmark = pytest.mark.unit


class TestTranslationCandidatesWorker:
    def test_returns_candidates_and_preferred(self):
        calls: list[tuple[str, str]] = []

        def fn(canonical: str, language: str) -> tuple[list[str], str | None]:
            calls.append((canonical, language))
            return (["青い目", "青目"], "青目")

        result = TranslationCandidatesWorker(fn, "blue_eyes", "ja", generation=3).execute()

        assert isinstance(result, TranslationCandidatesResult)
        assert result.candidates == ["青い目", "青目"]
        assert result.preferred == "青目"
        assert result.canonical == "blue_eyes"
        assert result.language == "ja"
        assert result.generation == 3
        assert calls == [("blue_eyes", "ja")]

    def test_degrades_to_empty_on_query_error(self):
        def fn(canonical: str, language: str) -> tuple[list[str], str | None]:
            raise ValueError("boom")

        result = TranslationCandidatesWorker(fn, "tag", "en").execute()

        assert result.candidates == []
        assert result.preferred is None
        assert result.language == "en"

    def test_finished_signal_carries_result(self, qtbot):
        def fn(canonical: str, language: str) -> tuple[list[str], str | None]:
            return (["a"], None)

        worker = TranslationCandidatesWorker(fn, "tag", "ja")
        with qtbot.waitSignal(worker.finished, timeout=2000) as blocker:
            worker.run()
        result = blocker.args[0]
        assert result.candidates == ["a"]
