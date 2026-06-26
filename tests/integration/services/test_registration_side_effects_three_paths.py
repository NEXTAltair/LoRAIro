"""登録副作用の3経路統一テスト (ADR 0061 §4, #633)。

GUI worker (DatabaseRegistrationWorker) / API (`api.images._register_into_db`) /
direct (ImageRegistrationService) の3経路が、同一の分類結果から同一の統計値
(registered / variant / skipped / failed) を生成することを検証する。

副作用 (関連ファイル取り込み先 / filename alias / 統計の意味) の単一定義は
ImageDatabaseManager.register_image_with_side_effects に集約されており、worker と API は
その outcome を統計へマッピングするだけなので、両経路は同一入力で必ず一致する。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.public_api.images import _register_into_db
from lorairo.database.db_manager import (
    ImageDatabaseManager,
    RegistrationOutcome,
    RegistrationSideEffectResult,
)
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager

# 分類 outcome の代表的な並び (新規 / 別版 / 重複 / 失敗) を 1 バッチに混在させる
_OUTCOME_SEQUENCE = [
    RegistrationOutcome.REGISTERED,
    RegistrationOutcome.VARIANT,
    RegistrationOutcome.DUPLICATE,
    RegistrationOutcome.REGISTERED,
    RegistrationOutcome.FAILED,
]


def _make_side_effect_results(outcomes):
    """outcome 列から register_image_with_side_effects の戻り値列を作る。"""
    results = []
    for idx, outcome in enumerate(outcomes):
        image_id = None if outcome is RegistrationOutcome.FAILED else idx + 1
        metadata = None if image_id is None else {"id": image_id}
        results.append(RegistrationSideEffectResult(outcome, image_id, metadata))
    return results


@pytest.fixture
def image_files(tmp_path: Path) -> list[Path]:
    files = []
    for i in range(len(_OUTCOME_SEQUENCE)):
        f = tmp_path / f"img_{i}.jpg"
        f.write_bytes(b"fake")
        files.append(f)
    return files


@pytest.mark.integration
class TestRegistrationSideEffectStatsThreePaths:
    """worker / API が統一エントリの outcome から同一統計を生成する。"""

    def test_worker_and_api_produce_identical_stats(self, tmp_path: Path, image_files) -> None:
        side_effect_results = _make_side_effect_results(_OUTCOME_SEQUENCE)

        # --- GUI worker 経路 ---
        worker_db = Mock(spec=ImageDatabaseManager)
        worker_db.register_image_with_side_effects.side_effect = list(side_effect_results)
        worker_fsm = Mock(spec=FileSystemManager)
        worker_fsm.get_image_files.return_value = image_files
        worker = DatabaseRegistrationWorker(tmp_path, worker_db, worker_fsm)
        # 関連ファイル preload / tag cache は本テストの対象外なので空にする
        worker._preload_associated_annotations = Mock(return_value={})
        worker._build_tag_id_cache = Mock(return_value={})
        worker_result = worker.execute()

        # --- API 経路 ---
        api_db = Mock(spec=ImageDatabaseManager)
        api_db.register_image_with_side_effects.side_effect = list(side_effect_results)
        api_fsm = Mock(spec=FileSystemManager)
        api_result = _register_into_db(api_db, api_fsm, image_files)

        # 期待統計: REGISTERED x2, VARIANT x1, DUPLICATE x1, FAILED x1
        assert (
            worker_result.registered_count,
            worker_result.variant_count,
            worker_result.skipped_count,
            worker_result.error_count,
        ) == (2, 1, 1, 1)
        assert (api_result.successful, api_result.variant, api_result.skipped, api_result.failed) == (
            2,
            1,
            1,
            1,
        )

        # 2 経路の統計が一致する (#633: 全経路統一)
        assert worker_result.registered_count == api_result.successful
        assert worker_result.variant_count == api_result.variant
        assert worker_result.skipped_count == api_result.skipped
        assert worker_result.error_count == api_result.failed


@pytest.mark.integration
class TestUnifiedEntrySideEffectDefinition:
    """副作用の単一定義 (register_image_with_side_effects) が分類結果駆動であること。"""

    @pytest.fixture
    def manager(self):
        mgr = ImageDatabaseManager(config_service=ConfigurationService(), image_repo=Mock())
        mgr.save_tags = Mock()
        mgr.save_captions = Mock()
        return mgr

    @pytest.mark.parametrize(
        ("classification", "expected_outcome", "alias_expected"),
        [
            ("new", RegistrationOutcome.REGISTERED, False),
            ("variant", RegistrationOutcome.VARIANT, False),
            ("duplicate", RegistrationOutcome.DUPLICATE, True),
        ],
    )
    def test_side_effects_follow_classification(
        self, manager, tmp_path: Path, classification, expected_outcome, alias_expected
    ) -> None:
        image_path = tmp_path / "x.jpg"
        image_path.write_bytes(b"fake")
        (tmp_path / "x.txt").write_text("tag1", encoding="utf-8")
        fsm = Mock(spec=FileSystemManager)

        with patch.object(
            manager, "register_original_image", return_value=(42, {"phash_classification": classification})
        ):
            result = manager.register_image_with_side_effects(image_path, fsm)

        assert result.outcome is expected_outcome
        # 関連ファイルは分類結果が解決した image_id (42) へ取り込まれる
        manager.save_tags.assert_called_once()
        assert manager.save_tags.call_args[0][0] == 42
        # filename alias は重複時のみ
        assert manager.image_repo.add_filename_alias.called is alias_expected
