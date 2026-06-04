# src/lorairo/gui/controllers/export_controller.py
"""データセットエクスポート制御Controller

MainWindowのexport_data()メソッドから分離。
エクスポートダイアログの表示とワークフローを担当。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QWidget

from ...utils.log import logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...services.selection_state_service import SelectionStateService
    from ...services.service_container import ServiceContainer


class ExportController:
    """データセットエクスポート制御Controller

    ADR 0055: エクスポート対象＝ステージング集合（明示的・有界・可視の名前付き集合）。
    ``staged_ids_provider`` を注入すると対象解決をステージング集合に切り替え、
    ワークスペース下部バーの件数表示（``StagingWidget.staged_images_changed``）と
    実エクスポート対象を一致させる。未注入時は従来の選択ベース解決にフォールバック
    する（後方互換）。

    Args:
        selection_state_service: 画像選択状態管理サービス
        service_container: サービスコンテナ
        parent: 親ウィジェット（MainWindow）
        staged_ids_provider: ステージング画像 ID を返す callable。注入時は対象解決を
            ステージング集合に切り替える（ADR 0055）。``None`` の場合は従来の選択ベース。
    """

    def __init__(
        self,
        selection_state_service: SelectionStateService | None,
        service_container: ServiceContainer,
        parent: QWidget | None = None,
        staged_ids_provider: Callable[[], list[int]] | None = None,
    ):
        self.selection_state_service = selection_state_service
        self.service_container = service_container
        self.parent = parent
        self.staged_ids_provider = staged_ids_provider

    def _validate_services(self) -> bool:
        """必須サービスの検証

        Returns:
            bool: 全サービスが有効な場合True
        """
        if not self.selection_state_service:
            logger.warning("SelectionStateServiceが初期化されていません")
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "SelectionStateServiceが初期化されていないため、画像選択情報を取得できません。",
                )
            return False

        return True

    def open_export_dialog(self) -> None:
        """エクスポートダイアログを開く"""
        try:
            # 選択画像ID取得
            current_image_ids = self._get_current_selected_images()

            if not current_image_ids:
                if self.staged_ids_provider is not None:
                    # ADR 0055: 対象＝ステージング集合。空ならステージングへの投入を促す。
                    message = (
                        "エクスポートする画像がステージングにありません。\n"
                        "サムネイルで画像を選択して『選択をステージングへ』で追加してください。"
                    )
                else:
                    message = (
                        "エクスポートする画像が選択されていません。\n"
                        "フィルタリング条件を設定して画像を表示するか、\n"
                        "サムネイル表示で画像を選択してください。"
                    )
                QMessageBox.warning(self.parent, "エクスポート", message)
                return

            logger.info(f"データセットエクスポート開始: {len(current_image_ids)}画像")

            # エクスポートダイアログ作成・表示
            from ..widgets.dataset_export_widget import DatasetExportWidget

            export_dialog = DatasetExportWidget(
                service_container=self.service_container,
                initial_image_ids=current_image_ids,
                parent=self.parent,
            )

            # 完了シグナル接続
            export_dialog.export_completed.connect(self._on_export_completed)

            # モーダルダイアログ表示
            export_dialog.exec()

        except Exception as e:
            error_msg = f"データセットエクスポート画面の表示に失敗しました: {e!s}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(
                    self.parent, "エラー", f"エクスポート機能の起動に失敗しました。\n\n{e!s}"
                )

    def _get_current_selected_images(self) -> list[int]:
        """エクスポート対象の画像IDリストを取得する。

        ADR 0055: ``staged_ids_provider`` 注入時はステージング集合を対象とする
        （ワークスペース下部バーの件数表示と同一ソース）。未注入時は従来どおり
        ``SelectionStateService`` の選択ベースで解決する（後方互換）。

        Returns:
            list[int]: 画像IDリスト
        """
        # ADR 0055: ステージング集合を優先（注入時）
        if self.staged_ids_provider is not None:
            staged_ids = self.staged_ids_provider() or []
            return list(staged_ids)

        # 後方互換: provider 未注入時は選択ベース
        if not self._validate_services():
            return []

        assert self.selection_state_service is not None
        return self.selection_state_service.get_current_selected_images()

    def _on_export_completed(self, path: str) -> None:
        """エクスポート完了ハンドラ

        Args:
            path: エクスポート先パス
        """
        logger.info(f"データセットエクスポート完了: {path}")
