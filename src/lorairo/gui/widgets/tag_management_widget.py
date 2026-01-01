"""タグ管理Widget

このモジュールはunknown typeタグの表示とtype変更機能を提供します。
"""

import threading

from genai_tag_db_tools.models import TagRecordPublic, TagTypeUpdate
from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QMessageBox, QTableWidgetItem, QWidget

from ...services.tag_management_service import TagManagementService
from ..designer.TagManagementWidget_ui import Ui_TagManagementWidget


class TagManagementWidget(QWidget, Ui_TagManagementWidget):
    """タグ管理Widget

    TagManagementServiceを使用してunknown typeタグの表示と一括更新を行います。

    Signals:
        update_completed: タグ更新完了時に発火
        update_failed (str): タグ更新失敗時に発火（エラーメッセージ）
    """

    # Signal定義
    update_completed = Signal()
    update_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        """TagManagementWidgetを初期化します

        Args:
            parent: 親Widget
        """
        super().__init__(parent)
        self.setupUi(self)  # type: ignore  # Justification: Qt Designer generated method

        # 依存注入
        self.tag_service: TagManagementService | None = None

        # 状態管理
        self.unknown_tags: list[TagRecordPublic] = []
        self.available_types: list[str] = []
        self._type_selections: dict[int, str] = {}  # tag_id -> new type_name

        # UI初期化
        self._setup_table_properties()
        self._connect_signals()

        logger.info("TagManagementWidget initialized")

    def set_tag_service(self, service: TagManagementService) -> None:
        """TagManagementServiceを依存注入します

        Args:
            service: TagManagementServiceインスタンス
        """
        self.tag_service = service
        logger.info("TagManagementService set for TagManagementWidget")

    def _setup_table_properties(self) -> None:
        """テーブルのプロパティを設定します"""
        # カラム幅を設定
        self.tableWidgetTags.setColumnWidth(0, 60)  # 選択 (checkbox)
        self.tableWidgetTags.setColumnWidth(1, 200)  # Tag
        self.tableWidgetTags.setColumnWidth(2, 200)  # Source Tag
        self.tableWidgetTags.setColumnWidth(3, 120)  # Current Type
        self.tableWidgetTags.setColumnWidth(4, 150)  # New Type (combobox)

    def _connect_signals(self) -> None:
        """Signalを接続します"""
        self.buttonUpdate.clicked.connect(self._on_update_clicked)
        self.update_completed.connect(self._on_update_completed)
        self.update_failed.connect(self._on_update_failed)

    def load_unknown_tags(self) -> None:
        """unknown typeタグを読み込みます

        TagManagementService APIを呼び出してunknown typeタグを取得し、テーブルに表示します。
        """
        if not self.tag_service:
            logger.error("TagManagementService not set")
            QMessageBox.warning(self, "エラー", "サービス接続が設定されていません。")
            return

        try:
            # TagManagementService API呼び出し
            self.unknown_tags = self.tag_service.get_unknown_tags()
            self.available_types = self.tag_service.get_all_available_types()

            logger.info(f"Loaded {len(self.unknown_tags)} unknown type tags")

            # テーブル表示更新
            self._update_table_display()

            # ステータス更新
            self.labelStatus.setText(f"Status: {len(self.unknown_tags)} unknown type tags found")

        except Exception as e:
            logger.error(f"Error loading unknown tags: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"unknown typeタグの読み込みに失敗しました:\n{e}",
            )

    def _update_table_display(self) -> None:
        """テーブル表示を更新します"""
        self.tableWidgetTags.setRowCount(0)  # クリア
        self._type_selections.clear()

        for row_idx, tag in enumerate(self.unknown_tags):
            self.tableWidgetTags.insertRow(row_idx)

            # Column 0: Checkbox (選択)
            checkbox = QCheckBox()
            checkbox.setProperty("tag_id", tag.tag_id)
            checkbox.stateChanged.connect(self._on_checkbox_changed)
            self.tableWidgetTags.setCellWidget(row_idx, 0, checkbox)

            # Column 1: Tag
            tag_item = QTableWidgetItem(tag.tag)
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tableWidgetTags.setItem(row_idx, 1, tag_item)

            # Column 2: Source Tag
            source_tag_item = QTableWidgetItem(tag.source_tag or "")
            source_tag_item.setFlags(source_tag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tableWidgetTags.setItem(row_idx, 2, source_tag_item)

            # Column 3: Current Type
            current_type_item = QTableWidgetItem(tag.type_name)
            current_type_item.setFlags(current_type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tableWidgetTags.setItem(row_idx, 3, current_type_item)

            # Column 4: New Type (QComboBox)
            combobox = QComboBox()
            combobox.addItem("(選択してください)", None)  # デフォルト
            for type_name in self.available_types:
                if type_name != "unknown":  # unknown以外を選択肢に追加
                    combobox.addItem(type_name, type_name)
            combobox.setProperty("tag_id", tag.tag_id)
            combobox.currentIndexChanged.connect(self._on_type_selection_changed)
            self.tableWidgetTags.setCellWidget(row_idx, 4, combobox)

        logger.debug(f"Table updated with {len(self.unknown_tags)} rows")

    def _on_checkbox_changed(self, state: int) -> None:
        """Checkbox状態変更時の処理"""
        self._update_button_state()

    def _on_type_selection_changed(self, index: int) -> None:
        """Type選択変更時の処理"""
        sender = self.sender()
        if isinstance(sender, QComboBox):
            tag_id = sender.property("tag_id")
            type_name = sender.currentData()

            if type_name:
                self._type_selections[tag_id] = type_name
            else:
                self._type_selections.pop(tag_id, None)

            self._update_button_state()

    def _update_button_state(self) -> None:
        """更新ボタンの有効/無効を切り替えます"""
        # 選択されたcheckboxとtype selectionがあるか確認
        has_selection = False
        for row in range(self.tableWidgetTags.rowCount()):
            checkbox = self.tableWidgetTags.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                tag_id = checkbox.property("tag_id")
                if tag_id in self._type_selections:
                    has_selection = True
                    break

        self.buttonUpdate.setEnabled(has_selection)

    def _on_update_clicked(self) -> None:
        """更新ボタンクリック時の処理 - 一括更新実行"""
        if not self.tag_service:
            logger.error("TagManagementService not set")
            return

        # 選択されたタグとtype_nameを収集
        updates: list[TagTypeUpdate] = []
        for row in range(self.tableWidgetTags.rowCount()):
            checkbox = self.tableWidgetTags.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                tag_id = checkbox.property("tag_id")
                new_type = self._type_selections.get(tag_id)
                if new_type:
                    updates.append(TagTypeUpdate(tag_id=tag_id, type_name=new_type))

        if not updates:
            QMessageBox.warning(
                self,
                "警告",
                "更新するタグが選択されていません。\nタグを選択し、新しいtypeを指定してください。",
            )
            return

        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            f"{len(updates)}個のタグのtypeを更新します。\n実行してよろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # UI無効化
        self.buttonUpdate.setEnabled(False)
        self.labelStatus.setText("Status: Updating...")

        # QThreadでシンプルに実行（Worker class不要）
        def run_update():
            try:
                self.tag_service.update_tag_types(updates)
                self.update_completed.emit()
            except Exception as e:
                logger.error(f"Error updating tag types: {e}", exc_info=True)
                self.update_failed.emit(str(e))

        thread = threading.Thread(target=run_update, daemon=True)
        thread.start()

        logger.info(f"Started updating {len(updates)} tags")

    def _on_update_completed(self) -> None:
        """更新完了時の処理"""
        logger.info("Tag type update completed successfully")

        QMessageBox.information(
            self,
            "完了",
            "タグのtype更新が完了しました。",
        )

        # テーブル再読み込み
        self.load_unknown_tags()

    def _on_update_failed(self, error_message: str) -> None:
        """更新失敗時の処理"""
        logger.error(f"Tag type update failed: {error_message}")

        QMessageBox.critical(
            self,
            "エラー",
            f"タグのtype更新に失敗しました:\n{error_message}",
        )

        # UI再有効化
        self.buttonUpdate.setEnabled(True)
        self.labelStatus.setText("Status: Update failed")
