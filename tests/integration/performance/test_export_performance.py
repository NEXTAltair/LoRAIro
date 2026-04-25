"""DatasetExportService 21,000件規模エクスポートパフォーマンステスト。

export_with_criteria() が大量データに対して規定時間・メモリ内で完了することを計測・記録する。
基準値超過はテスト失敗ではなく警告のみ（CI 環境依存が大きいため）。
"""

import time
import tracemalloc
import uuid
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.schema import Base, Image, ModelType, Project
from lorairo.services.dataset_export_service import DatasetExportService
from lorairo.storage.file_system import FileSystemManager


@pytest.mark.slow
@pytest.mark.integration
class TestExportPerformance:
    """21,000件規模のエクスポートパフォーマンステスト。

    CI の通常実行では -m "not slow" で除外される。
    基準値超過時はテストを失敗させず、計測値を記録して警告を出す。
    """

    TOTAL_IMAGES = 21_000
    TARGET_SECONDS = 30
    TARGET_MB = 500

    @pytest.fixture(scope="class")
    def perf_db(self, tmp_path_factory):
        """21,000件の画像データを持つ SQLite DB を 1 回だけ作成し、image_id リストを返す。

        scope="class" によりクラス内の全テストで再利用される。
        """
        db_path = tmp_path_factory.mktemp("perf_db") / "perf_test.db"
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)

        with SessionLocal() as session:
            # ModelType 初期データ
            for tname in ["tagger", "multimodal", "score", "rating"]:
                session.add(ModelType(name=tname))
            session.flush()

            # Project 作成
            project = Project(name="perf_test", path=str(db_path.parent))
            session.add(project)
            session.flush()

            # 21,000件を bulk_insert_mappings で高速挿入
            session.bulk_insert_mappings(
                Image,
                [
                    {
                        "uuid": str(uuid.uuid4()),
                        "phash": f"phash_{i:08d}",
                        "original_image_path": f"/tmp/orig_{i}.webp",
                        "stored_image_path": f"image_dataset/512/2024/01/01/img_{i:05d}.webp",
                        "width": 512,
                        "height": 512,
                        "format": "webp",
                        "extension": "webp",
                        "project_id": project.id,
                    }
                    for i in range(self.TOTAL_IMAGES)
                ],
            )
            session.commit()

            image_ids = [row.id for row in session.query(Image.id).all()]

        yield image_ids

        engine.dispose()

    def _build_mock_db_manager(self, image_ids: list[int]) -> Mock:
        """21,000件分のモック DB マネージャーを構築する。

        Args:
            image_ids: DB に挿入された実際の image_id リスト。

        Returns:
            設定済みの Mock オブジェクト。
        """
        mock_db_manager = Mock()

        # get_images_by_filter: criteria を受け取り全 image_id を返す
        def get_images_side_effect(criteria: ImageFilterCriteria):
            images = [
                {
                    "id": iid,
                    "stored_image_path": f"image_dataset/512/2024/01/01/img_{iid:05d}.webp",
                    "filename": f"img_{iid:05d}.webp",
                }
                for iid in image_ids
            ]
            return images, len(images)

        mock_db_manager.get_images_by_filter.side_effect = get_images_side_effect

        # get_image_metadata: 各 ID の最低限メタデータを返す
        def get_metadata_side_effect(image_id: int):
            return {
                "id": image_id,
                "width": 512,
                "height": 512,
                "format": "webp",
                "stored_image_path": f"image_dataset/512/2024/01/01/img_{image_id:05d}.webp",
            }

        mock_db_manager.get_image_metadata.side_effect = get_metadata_side_effect

        # check_processed_image_exists: resolution=512 の場合のみ有効
        def check_processed_side_effect(image_id: int, resolution: int):
            if resolution == 512:
                return {"stored_image_path": f"image_dataset/512/2024/01/01/img_{image_id:05d}.webp"}
            return None

        mock_db_manager.check_processed_image_exists.side_effect = check_processed_side_effect

        # get_tags: 全件同じ "cat" タグ
        def get_tags_side_effect(image_id: int):
            return [{"tag": "cat", "tag_id": 1001, "confidence_score": 0.9}]

        mock_db_manager.get_tags.side_effect = get_tags_side_effect

        # get_captions: 全件同じキャプション
        def get_captions_side_effect(image_id: int):
            return [{"caption": "a cat", "confidence_score": 0.9}]

        mock_db_manager.get_captions.side_effect = get_captions_side_effect

        # get_image_annotations: tags + captions をまとめて返す
        def get_annotations_side_effect(image_id: int):
            return {
                "tags": get_tags_side_effect(image_id),
                "captions": get_captions_side_effect(image_id),
            }

        mock_db_manager.get_image_annotations.side_effect = get_annotations_side_effect

        # get_batch_available_resolutions
        def get_batch_resolutions_side_effect(ids: list[int]):
            return {iid: [512] for iid in ids}

        mock_db_manager.get_batch_available_resolutions.side_effect = get_batch_resolutions_side_effect

        return mock_db_manager

    def test_export_21k_images_performance(self, perf_db: list[int], tmp_path: Path) -> None:
        """21,000件エクスポートが TARGET_SECONDS 秒以内・TARGET_MB MB以内で完了する。

        基準値超過時はテストを失敗させず、計測値を標準出力と警告に記録する。

        Args:
            perf_db: 21,000件の image_id リスト（class スコープフィクスチャ）。
            tmp_path: pytest が提供する一時出力ディレクトリ。
        """
        image_ids = perf_db
        assert len(image_ids) == self.TOTAL_IMAGES, (
            f"DB 挿入件数が想定と異なります: {len(image_ids)} != {self.TOTAL_IMAGES}"
        )

        # --- サービスのセットアップ ---
        mock_config_service = Mock()
        mock_config_service.get_database_directory.return_value = str(tmp_path)

        file_system_manager = FileSystemManager()
        mock_db_manager = self._build_mock_db_manager(image_ids)
        mock_search_processor = Mock()

        output_dir = tmp_path / "export_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        service = DatasetExportService(
            config_service=mock_config_service,
            file_system_manager=file_system_manager,
            db_manager=mock_db_manager,
            search_processor=mock_search_processor,
        )

        criteria = ImageFilterCriteria()

        # --- 計測開始 ---
        tracemalloc.start()
        start_time = time.perf_counter()

        # _resolve_processed_image_path をモックして実ファイルアクセスをスキップ。
        # copy_file もモックして実際のファイルコピーを行わない。
        # これにより txt/caption ファイルの書き込みのみを計測対象とする。
        with (
            patch.object(
                service,
                "_resolve_processed_image_path",
                side_effect=lambda image_id, resolution: (
                    Path(f"image_dataset/512/2024/01/01/img_{image_id:05d}.webp")
                    if resolution == 512
                    else None
                ),
            ),
            patch.object(file_system_manager, "copy_file"),
        ):
            with warnings.catch_warnings():
                # DeprecationWarning (image_ids パラメータ) を抑制してクリーンな出力にする
                warnings.simplefilter("ignore", DeprecationWarning)
                result_path = service.export_with_criteria(
                    output_path=output_dir,
                    format_type="txt",
                    resolution=512,
                    criteria=criteria,
                )

        elapsed = time.perf_counter() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak / (1024 * 1024)

        # --- 結果の記録 ---
        perf_summary = (
            f"[PERF] images={len(image_ids)}, "
            f"elapsed={elapsed:.2f}s (target<{self.TARGET_SECONDS}s), "
            f"peak_memory={peak_mb:.1f}MB (target<{self.TARGET_MB}MB)"
        )
        print(f"\n{perf_summary}")

        # 基準値超過は失敗にせず、pytest.warns 互換の warnings として記録する
        if elapsed > self.TARGET_SECONDS:
            warnings.warn(
                f"パフォーマンス基準超過: elapsed={elapsed:.2f}s > {self.TARGET_SECONDS}s. {perf_summary}",
                UserWarning,
                stacklevel=2,
            )
        if peak_mb > self.TARGET_MB:
            warnings.warn(
                f"メモリ基準超過: peak_memory={peak_mb:.1f}MB > {self.TARGET_MB}MB. {perf_summary}",
                UserWarning,
                stacklevel=2,
            )

        # 出力パスが正しく返っていることだけ確認（動作保証）
        assert result_path == output_dir, f"エクスポート先パスが想定と異なります: {result_path}"
        # 少なくとも 1 件はエクスポートされていることを確認
        txt_files = list(output_dir.glob("*.txt"))
        assert len(txt_files) > 0, "TXT ファイルが 1 件も出力されていません"
        assert len(txt_files) == self.TOTAL_IMAGES, (
            f"出力 TXT ファイル件数が想定と異なります: {len(txt_files)} != {self.TOTAL_IMAGES}"
        )
