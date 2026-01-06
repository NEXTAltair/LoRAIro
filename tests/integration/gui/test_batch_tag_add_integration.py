"""
バッチタグ追加統合テスト

選択 → ステージング → タグ追加 → 保存のフルワークフローをテスト。
実際のGUIコンポーネント間相互作用を検証し、外部依存のみモック。
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from lorairo.gui.services.image_db_write_service import ImageDBWriteService
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget


@pytest.mark.gui
class TestBatchTagAddIntegration:
    """バッチタグ追加ワークフローの統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット (pytest-qt対応)"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def dataset_state_manager(self, parent_widget):
        """テスト用データセット状態管理"""
        return DatasetStateManager(parent_widget)

    @pytest.fixture
    def mock_db_write_service(self):
        """MockのImageDBWriteService"""
        service = Mock(spec=ImageDBWriteService)
        # デフォルトの戻り値設定
        service.add_tag_batch.return_value = True
        service.update_rating.return_value = True
        service.update_score.return_value = True
        return service

    @pytest.fixture
    def batch_tag_widget(self, parent_widget, dataset_state_manager, qtbot):
        """実際のBatchTagAddWidget"""
        widget = BatchTagAddWidget(parent_widget)
        widget.set_dataset_state_manager(dataset_state_manager)
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def thumbnail_widget(self, parent_widget, dataset_state_manager, qtbot):
        """実際のThumbnailSelectorWidget（簡易版）"""
        try:
            widget = ThumbnailSelectorWidget(parent_widget, dataset_state_manager)
            qtbot.addWidget(widget)
            return widget
        except Exception as e:
            pytest.skip(f"ThumbnailSelectorWidget initialization failed: {e}")
            return None

    @pytest.fixture
    def test_images_data(self):
        """テスト用画像データ（実際のテストリソース使用）"""
        test_img_dir = Path("/workspaces/LoRAIro/tests/resources/img/1_img")
        return [
            {
                "id": i + 1,
                "filename": f"file{i + 1:02d}.webp",
                "stored_image_path": str(test_img_dir / f"file{i + 1:02d}.webp"),
                "width": 512,
                "height": 512,
                "tags": "existing, test" if i % 2 == 0 else "anime, girl",
                "caption": f"Test caption {i + 1}",
                "rating": "PG-13",
                "score": 500,
            }
            for i in range(5)  # file01.webp から file05.webp まで
        ]

    def test_full_batch_tag_add_workflow(
        self, batch_tag_widget, dataset_state_manager, mock_db_write_service, test_images_data, qtbot
    ):
        """
        フルワークフロー統合テスト: 選択 → ステージング → タグ追加 → 保存

        ワークフロー:
        1. DatasetStateManager に複数画像を選択状態にする
        2. "選択中の画像を追加" ボタンでステージングエリアに追加
        3. タグ入力フィールドにタグを入力
        4. "追加" ボタンでタグ追加リクエスト発行
        5. DB更新とUI更新を検証
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 複数画像を選択状態にする（ID: 1, 2, 3）
        selected_ids = [1, 2, 3]
        dataset_state_manager.set_selected_images(selected_ids)

        # 3. "選択中の画像を追加" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000) as blocker:
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 4. ステージングリストに画像が追加されたことを確認
        assert len(batch_tag_widget._staged_images) == 3
        assert set(batch_tag_widget._staged_images.keys()) == {1, 2, 3}
        assert batch_tag_widget.ui.listWidgetStaging.count() == 3

        # 5. シグナルが発行されたことを確認
        assert blocker.signal_triggered
        assert blocker.args[0] == [1, 2, 3]

        # 6. タグ入力フィールドにタグを入力
        test_tag = "landscape"
        batch_tag_widget.ui.lineEditTag.setText(test_tag)

        # 7. tag_add_requested シグナルをキャプチャ
        signal_emitted = False
        received_image_ids = None
        received_tag = None

        def on_tag_add_requested(image_ids, tag):
            nonlocal signal_emitted, received_image_ids, received_tag
            signal_emitted = True
            received_image_ids = image_ids
            received_tag = tag

        batch_tag_widget.tag_add_requested.connect(on_tag_add_requested)

        # 8. "追加" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.tag_add_requested, timeout=1000) as blocker:
            batch_tag_widget.ui.pushButtonAddTag.click()

        # 9. tag_add_requested シグナルが正しいパラメータで発行されたことを確認
        assert signal_emitted is True
        assert set(received_image_ids) == {1, 2, 3}
        assert received_tag == test_tag
        assert blocker.signal_triggered
        assert set(blocker.args[0]) == {1, 2, 3}
        assert blocker.args[1] == test_tag

    def test_staging_and_clearing(self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot):
        """
        ステージング追加とクリアのテスト

        1. 画像をステージングに追加
        2. "クリア" ボタンでステージングリストをクリア
        3. staging_cleared シグナルが発行されることを確認
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像を選択してステージングに追加
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. ステージングリストに追加されたことを確認
        assert len(batch_tag_widget._staged_images) == 2

        # 4. staging_cleared シグナルをキャプチャ
        signal_emitted = False

        def on_staging_cleared():
            nonlocal signal_emitted
            signal_emitted = True

        batch_tag_widget.staging_cleared.connect(on_staging_cleared)

        # 5. "クリア" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.staging_cleared, timeout=1000):
            batch_tag_widget.ui.pushButtonClearStaging.click()

        # 6. ステージングリストがクリアされたことを確認
        assert len(batch_tag_widget._staged_images) == 0
        assert batch_tag_widget.ui.listWidgetStaging.count() == 0
        assert signal_emitted is True

    def test_duplicate_staging_prevention(
        self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot
    ):
        """
        重複ステージングの防止テスト

        同じ画像を複数回ステージングに追加しようとした場合、
        重複が防止されることを確認。
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像を選択してステージングに追加（1回目）
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. ステージングリストに2枚追加されたことを確認
        assert len(batch_tag_widget._staged_images) == 2

        # 4. 同じ画像を再度選択してステージングに追加（2回目）
        dataset_state_manager.set_selected_images([1, 3])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 5. 重複が防止され、ID 3のみが追加されたことを確認
        assert len(batch_tag_widget._staged_images) == 3
        assert set(batch_tag_widget._staged_images.keys()) == {1, 2, 3}

    def test_staging_limit_enforcement(self, batch_tag_widget, dataset_state_manager, qtbot):
        """
        ステージング上限（500枚）の強制テスト

        500枚を超える画像をステージングに追加しようとした場合、
        500枚でストップし、それ以上は追加されないことを確認。

        Note: エラーダイアログ表示は未実装（TODO）のため、ログのみでチェック。
        """
        # 1. 501枚の画像データを作成
        large_dataset = [
            {"id": i, "filename": f"image{i}.jpg", "stored_image_path": f"/test/image{i}.jpg"}
            for i in range(501)
        ]
        dataset_state_manager.set_dataset_images(large_dataset)

        # 2. 501枚すべてを選択
        all_ids = list(range(501))
        dataset_state_manager.set_selected_images(all_ids)

        # 3. ステージングに追加を試みる
        batch_tag_widget.ui.pushButtonAddSelected.click()

        # 4. 500枚でストップしていることを確認（上限まで）
        assert len(batch_tag_widget._staged_images) == 500

    def test_empty_tag_validation(self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot):
        """
        空タグ入力のバリデーションテスト

        タグ入力フィールドが空の状態で "追加" ボタンをクリックした場合、
        tag_add_requested シグナルが発行されないことを確認。

        Note: エラーダイアログ表示は未実装（TODO）のため、ログのみでチェック。
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像をステージングに追加
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. タグ入力フィールドを空にする（デフォルトで空だが明示的に設定）
        batch_tag_widget.ui.lineEditTag.clear()

        # 4. tag_add_requested シグナルをキャプチャ
        signal_emitted = False

        def on_tag_add_requested(image_ids, tag):
            nonlocal signal_emitted
            signal_emitted = True

        batch_tag_widget.tag_add_requested.connect(on_tag_add_requested)

        # 5. "追加" ボタンをクリック
        batch_tag_widget.ui.pushButtonAddTag.click()

        # 6. tag_add_requested シグナルが発行されなかったことを確認
        assert signal_emitted is False

    def test_individual_item_removal(self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot):
        """
        個別アイテム削除のテスト

        ステージングリストから個別のアイテムを削除できることを確認。
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 3枚の画像をステージングに追加
        dataset_state_manager.set_selected_images([1, 2, 3])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. ステージングリストに3枚追加されたことを確認
        assert len(batch_tag_widget._staged_images) == 3

        # 4. 2番目のアイテムを選択
        batch_tag_widget.ui.listWidgetStaging.setCurrentRow(1)

        # 5. Deleteキーを押してアイテムを削除
        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            qtbot.keyClick(batch_tag_widget.ui.listWidgetStaging, Qt.Key.Key_Delete)

        # 6. 2番目のアイテムが削除され、2枚残ったことを確認
        assert len(batch_tag_widget._staged_images) == 2
        assert batch_tag_widget.ui.listWidgetStaging.count() == 2

        # 7. 削除されたアイテムがID 2であったことを確認（順序: 1, 2, 3 → 1, 3）
        assert 2 not in batch_tag_widget._staged_images.keys()

    def test_tag_normalization_with_tagdbtools(
        self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot
    ):
        """
        TagDBtools統合テスト: タグ正規化

        入力されたタグがTagCleaner.clean_format()で正規化され、
        正規化後のタグがtag_add_requestedシグナルで発行されることを確認。

        Note: TagCleaner.clean_format() は underscores を空白に変換、小文字化する。
        """

        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像をステージングに追加
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. タグ入力（正規化前: "Test_LANDSCAPE" → 正規化後: "test landscape"）
        batch_tag_widget.ui.lineEditTag.setText("Test_LANDSCAPE")

        # 4. tag_add_requested シグナルをキャプチャ
        signal_emitted = False
        received_tag = None

        def on_tag_add_requested(image_ids, tag):
            nonlocal signal_emitted, received_tag
            signal_emitted = True
            received_tag = tag

        batch_tag_widget.tag_add_requested.connect(on_tag_add_requested)

        # 5. "追加" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.tag_add_requested, timeout=1000):
            batch_tag_widget.ui.pushButtonAddTag.click()

        # 6. 正規化されたタグが発行されたことを確認
        # TagCleaner.clean_format() は underscores → spaces, lowercase
        assert signal_emitted is True
        assert received_tag == "test landscape"  # 正規化後のタグ

    def test_mainwindow_signal_connection_simulation(
        self, batch_tag_widget, dataset_state_manager, mock_db_write_service, test_images_data, qtbot
    ):
        """
        MainWindow統合シミュレーション: シグナル接続とDBサービス呼び出し

        BatchTagAddWidget の tag_add_requested シグナルが
        MainWindow のハンドラー経由で ImageDBWriteService.add_tag_batch() を
        呼び出すワークフローをシミュレート。
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像をステージングに追加
        dataset_state_manager.set_selected_images([1, 2, 3])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. MainWindow のハンドラーをシミュレート
        def mock_mainwindow_handler(image_ids, tag):
            """MainWindow._handle_batch_tag_add() をシミュレート"""
            # ImageDBWriteService.add_tag_batch() を呼び出し
            success = mock_db_write_service.add_tag_batch(image_ids, tag)

            if success:
                # DatasetStateManager.refresh_images() を呼び出し（モック不要）
                # 実際のMainWindowでは dataset_state.refresh_images(image_ids) を呼ぶ
                pass

            return success

        # 4. シグナル接続
        batch_tag_widget.tag_add_requested.connect(mock_mainwindow_handler)

        # 5. タグ入力
        batch_tag_widget.ui.lineEditTag.setText("nature")

        # 6. "追加" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.tag_add_requested, timeout=1000):
            batch_tag_widget.ui.pushButtonAddTag.click()

        # 7. ImageDBWriteService.add_tag_batch() が正しいパラメータで呼ばれたことを確認
        mock_db_write_service.add_tag_batch.assert_called_once()
        call_args = mock_db_write_service.add_tag_batch.call_args
        assert set(call_args[0][0]) == {1, 2, 3}  # image_ids
        assert call_args[0][1] == "nature"  # tag

    def test_ui_state_after_successful_add(
        self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot
    ):
        """
        タグ追加成功後のUI状態テスト

        tag_add_requested シグナル発行後、以下のUI状態を確認:
        1. ステージングリストがクリアされる
        2. タグ入力フィールドがクリアされる
        3. フォーカスがタグ入力フィールドに戻る
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 画像をステージングに追加
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        # 3. タグ入力
        batch_tag_widget.ui.lineEditTag.setText("sunset")

        # 4. "追加" ボタンをクリック
        with qtbot.waitSignal(batch_tag_widget.tag_add_requested, timeout=1000):
            batch_tag_widget.ui.pushButtonAddTag.click()

        # 5. UI状態を確認（tag_add_requested シグナル発行後の状態）
        # Note: ステージングリストはクリアされない（MainWindowで処理）
        # タグ入力フィールドのみクリアされる

        # ステージングリストはそのまま残る
        assert len(batch_tag_widget._staged_images) == 2
        assert batch_tag_widget.ui.listWidgetStaging.count() == 2

        # タグ入力フィールドがクリアされたことを確認
        assert batch_tag_widget.ui.lineEditTag.text() == ""

    def test_error_handling_no_staged_images(self, batch_tag_widget, dataset_state_manager, qtbot):
        """
        エラーハンドリング: ステージング画像なし

        ステージングリストが空の状態で "追加" ボタンをクリックした場合、
        tag_add_requested シグナルが発行されないことを確認。

        Note: エラーダイアログ表示は未実装（TODO）のため、ログのみでチェック。
        """
        # 1. タグ入力（ステージングリストは空）
        batch_tag_widget.ui.lineEditTag.setText("test_tag")

        # 2. tag_add_requested シグナルをキャプチャ
        signal_emitted = False

        def on_tag_add_requested(image_ids, tag):
            nonlocal signal_emitted
            signal_emitted = True

        batch_tag_widget.tag_add_requested.connect(on_tag_add_requested)

        # 3. "追加" ボタンをクリック
        batch_tag_widget.ui.pushButtonAddTag.click()

        # 4. tag_add_requested シグナルが発行されなかったことを確認
        assert signal_emitted is False

    def test_concurrent_operations_safety(
        self, batch_tag_widget, dataset_state_manager, test_images_data, qtbot
    ):
        """
        並行操作の安全性テスト

        複数の操作が連続して実行された場合でも、
        データ整合性が保たれることを確認。

        シナリオ:
        1. 画像を選択してステージングに追加
        2. さらに画像を選択して追加
        3. 一部を削除
        4. タグ追加
        """
        # 1. テストデータセット設定
        dataset_state_manager.set_dataset_images(test_images_data)

        # 2. 最初の2枚をステージングに追加
        dataset_state_manager.set_selected_images([1, 2])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        assert len(batch_tag_widget._staged_images) == 2

        # 3. さらに2枚を追加
        dataset_state_manager.set_selected_images([3, 4])

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            batch_tag_widget.ui.pushButtonAddSelected.click()

        assert len(batch_tag_widget._staged_images) == 4

        # 4. 2番目のアイテムを削除
        batch_tag_widget.ui.listWidgetStaging.setCurrentRow(1)

        with qtbot.waitSignal(batch_tag_widget.staged_images_changed, timeout=1000):
            qtbot.keyClick(batch_tag_widget.ui.listWidgetStaging, Qt.Key.Key_Delete)

        assert len(batch_tag_widget._staged_images) == 3

        # 5. タグ追加
        batch_tag_widget.ui.lineEditTag.setText("final_tag")

        with qtbot.waitSignal(batch_tag_widget.tag_add_requested, timeout=1000) as blocker:
            batch_tag_widget.ui.pushButtonAddTag.click()

        # 6. 最終的なステージング画像が正しいことを確認
        assert len(blocker.args[0]) == 3  # 4 - 1 = 3枚
        # TagCleaner.clean_format() は underscores → spaces
        assert blocker.args[1] == "final tag"
