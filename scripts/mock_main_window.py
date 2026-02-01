from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QCheckBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))


def _make_panel_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: bold;")
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return label


def _make_placeholder(text: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return widget


def _get_mock_image_paths(limit: int = 6) -> list[Path]:
    img_dir = ROOT / "tests" / "resources" / "img" / "1_img"
    if not img_dir.exists():
        return []
    return list(img_dir.glob("*.webp"))[:limit]


def _build_mock_thumbnail_grid() -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    image_paths = _get_mock_image_paths()
    if not image_paths:
        layout.addWidget(_make_placeholder("画像サンプルが見つかりません"), 0, 0)
        return widget

    columns = 3
    thumb_size = QSize(120, 120)
    for index, path in enumerate(image_paths):
        row = index // columns
        col = index % columns
        item = QLabel()
        item.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            item.setPixmap(pixmap.scaled(thumb_size, Qt.AspectRatioMode.KeepAspectRatio))
        item.setToolTip(path.name)
        layout.addWidget(item, row, col)
    return widget


def _build_mock_staging_thumbnail_grid() -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    image_paths = _get_mock_image_paths(limit=6)
    if not image_paths:
        layout.addWidget(_make_placeholder("ステージング画像がありません"), 0, 0)
        return widget

    columns = 3
    thumb_size = QSize(96, 96)
    for index, path in enumerate(image_paths):
        row = index // columns
        col = index % columns
        item = QLabel()
        item.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            item.setPixmap(pixmap.scaled(thumb_size, Qt.AspectRatioMode.KeepAspectRatio))
        item.setToolTip(path.name)
        layout.addWidget(item, row, col)
    return widget


def _build_mock_filter_summary() -> QWidget:
    group = QGroupBox("検索プレビュー")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    layout.addWidget(QLabel("キーワード: landscape | Rating: PG-13 | 未タグ付きのみ"))
    layout.addWidget(QLabel("検索結果: 128 件"))
    return group


def _build_mock_annotation_filters() -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    group_function = QGroupBox("機能タイプ")
    function_layout = QHBoxLayout(group_function)
    function_layout.setSpacing(6)
    function_layout.addWidget(QCheckBox("Caption生成"))
    function_layout.addWidget(QCheckBox("Tag生成"))
    function_layout.addWidget(QCheckBox("品質スコア"))
    function_layout.addItem(
        QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    )
    layout.addWidget(group_function)

    group_provider = QGroupBox("実行環境選択")
    provider_layout = QHBoxLayout(group_provider)
    provider_layout.setSpacing(6)
    provider_layout.addWidget(QCheckBox("Web API"))
    provider_layout.addWidget(QCheckBox("ローカルモデル"))
    provider_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
    layout.addWidget(group_provider)

    return container


def _build_mock_model_selection_widget() -> QWidget:
    try:
        from lorairo.gui.designer.ModelSelectionWidget_ui import Ui_ModelSelectionWidget
        from lorairo.gui.widgets.model_checkbox_widget import ModelCheckboxWidget, ModelInfo
    except Exception:
        return _make_placeholder("ModelSelectionWidget UI (mock)")

    class _MockModelSelectionWidget(QWidget, Ui_ModelSelectionWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setupUi(self)
            self._populate_dummy_models()
            if hasattr(self, "statusLabel"):
                self.statusLabel.setText("選択数: 0 (mock)")

        def _populate_dummy_models(self) -> None:
            if not hasattr(self, "dynamicContentLayout"):
                return

            if hasattr(self, "placeholderLabel"):
                self.placeholderLabel.setVisible(False)

            dummy_models = [
                ModelInfo(
                    name="gpt-4o-mini-vision",
                    provider="openai",
                    capabilities=["caption", "tags"],
                    requires_api_key=True,
                    is_local=False,
                ),
                ModelInfo(
                    name="claude-3.5-sonnet",
                    provider="anthropic",
                    capabilities=["caption", "tags"],
                    requires_api_key=True,
                    is_local=False,
                ),
                ModelInfo(
                    name="gemini-1.5-flash",
                    provider="google",
                    capabilities=["caption", "tags", "scores"],
                    requires_api_key=True,
                    is_local=False,
                ),
                ModelInfo(
                    name="wd-v1-4-swin-v2-tagger",
                    provider="local",
                    capabilities=["tags"],
                    requires_api_key=False,
                    is_local=True,
                ),
            ]

            grouped: dict[str, list[ModelInfo]] = {}
            for model in dummy_models:
                grouped.setdefault(model.provider, []).append(model)

            insert_index = max(0, self.dynamicContentLayout.count() - 1)
            for provider, models in grouped.items():
                header = QLabel(f"{provider.title()} Models")
                header.setProperty("class", "provider-group-label")
                self.dynamicContentLayout.insertWidget(insert_index, header)
                insert_index += 1
                for model in models:
                    self.dynamicContentLayout.insertWidget(
                        insert_index, ModelCheckboxWidget(model)
                    )
                    insert_index += 1

        def select_all_models(self) -> None:
            pass

        def deselect_all_models(self) -> None:
            pass

        def select_recommended_models(self) -> None:
            pass

    return _MockModelSelectionWidget()


def _build_top_dataset_selector() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)

    layout.addWidget(QLabel("データセット:"))
    path_edit = QLineEdit()
    path_edit.setPlaceholderText("データセットディレクトリを選択してください")
    path_edit.setReadOnly(True)
    layout.addWidget(path_edit, 1)

    layout.addWidget(QPushButton("選択"))
    layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
    layout.addWidget(QPushButton("設定"))
    return frame


def _build_db_status_bar() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 5, 10, 5)
    layout.setSpacing(6)
    label = QLabel("データベース: 未接続")
    label.setStyleSheet("font-weight: bold;")
    layout.addWidget(label)
    layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
    return frame


def _build_left_filter_panel() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    layout.addWidget(_make_panel_title("検索・フィルター"))
    layout.addWidget(_make_placeholder("FilterSearchPanel (mock)"))
    layout.addWidget(_build_mock_filter_summary())
    return frame


def _build_thumbnail_panel() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    layout.addWidget(_make_panel_title("サムネイル"))
    thumbnails = _build_mock_thumbnail_grid()
    layout.addWidget(thumbnails)

    staging_container = QWidget()
    staging_layout = QVBoxLayout(staging_container)
    staging_layout.setContentsMargins(0, 0, 0, 0)
    staging_layout.setSpacing(6)
    staging_layout.addWidget(_build_staging_panel())
    staging_group = QGroupBox("ステージング状況")
    staging_info_layout = QVBoxLayout(staging_group)
    staging_info_layout.addWidget(QLabel("編集対象: 0 件"))
    staging_info_layout.addWidget(QLabel("アノテーション対象: 0 件"))
    staging_layout.addWidget(staging_group)
    layout.addWidget(staging_container)

    layout.setStretch(1, 3)
    layout.setStretch(2, 1)
    return frame


def _build_right_panel() -> QWidget:
    from scripts.mock_right_panel import _build_right_panel as _build

    return _build()


def _build_action_toolbar() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 5, 10, 5)
    layout.setSpacing(8)
    layout.addWidget(QPushButton("アノテーション"))
    layout.addWidget(QPushButton("エクスポート"))
    layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
    layout.addWidget(QLabel("準備完了"))
    return frame


def _build_staging_panel() -> QWidget:
    group = QGroupBox("ステージング")
    layout = QVBoxLayout(group)
    list_widget = QListWidget()
    list_widget.setMinimumHeight(80)
    list_widget.setMaximumHeight(220)
    list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    image_paths = _get_mock_image_paths(limit=4)
    for path in image_paths:
        item = QListWidgetItem(path.name)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            icon = QIcon(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
            item.setIcon(icon)
        list_widget.addItem(item)
    _adjust_staging_height(list_widget)
    layout.addWidget(list_widget)
    layout.addWidget(QPushButton("選択中の画像を追加"))
    return group


def _adjust_staging_height(list_widget: QListWidget) -> None:
    rows = list_widget.count()
    if rows == 0:
        return
    row_height = list_widget.sizeHintForRow(0)
    header_padding = 16
    target = rows * row_height + header_padding
    min_h = list_widget.minimumHeight()
    max_h = list_widget.maximumHeight()
    list_widget.setMinimumHeight(max(min_h, min(target, max_h)))


def _build_batch_tag_tab() -> QWidget:
    from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, AnnotationDataDisplayWidget

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)
    layout.addWidget(_make_panel_title("バッチタグ追加"))

    columns = QHBoxLayout()
    columns.setSpacing(8)

    left = QGroupBox("ステージング画像")
    left_layout = QVBoxLayout(left)
    left_layout.addWidget(_build_mock_staging_thumbnail_grid())

    right = QGroupBox("操作")
    right_layout = QVBoxLayout(right)
    right_layout.addWidget(_make_placeholder("ステージング済み画像にタグ追加 (mock)"))

    tag_table = AnnotationDataDisplayWidget()
    if hasattr(tag_table, "tableWidgetTags"):
        tag_table.tableWidgetTags.setVisible(True)
    if hasattr(tag_table, "_tags_compact_label"):
        tag_table._tags_compact_label.setVisible(False)
    tag_table.set_group_box_visibility(caption=False, scores=False)
    tag_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    if hasattr(tag_table, "groupBoxTags"):
        tag_table.groupBoxTags.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
    if hasattr(tag_table, "verticalLayoutMain"):
        tag_table.verticalLayoutMain.setContentsMargins(0, 0, 0, 0)
    tag_table.update_data(
        AnnotationData(
            tags=[
                {
                    "tag": "1girl",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.95,
                    "is_edited_manually": False,
                },
                {
                    "tag": "solo",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.90,
                    "is_edited_manually": False,
                },
                {
                    "tag": "outdoor",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.88,
                    "is_edited_manually": True,
                },
            ],
            caption="",
        )
    )
    right_layout.addWidget(tag_table)

    annotation_group = QGroupBox("アノテーション")
    annotation_layout = QVBoxLayout(annotation_group)
    annotation_layout.addWidget(QLabel("対象: ステージング済み画像"))
    annotation_layout.addWidget(_build_mock_annotation_filters())
    annotation_layout.addWidget(_build_mock_model_selection_widget())
    annotation_layout.addWidget(_make_placeholder("アノテーション実行 (mock)"))
    right_layout.addWidget(annotation_group)

    columns.addWidget(left, 1)
    columns.addWidget(right, 1)
    layout.addLayout(columns, 1)
    return container


def _build_main_tabs() -> QTabWidget:
    tabs = QTabWidget()
    tabs.addTab(_build_main_splitter(), "ワークスペース")
    tabs.addTab(_build_batch_tag_tab(), "バッチタグ")
    return tabs


def _build_main_splitter() -> QSplitter:
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(_build_left_filter_panel())
    splitter.addWidget(_build_thumbnail_panel())
    splitter.addWidget(_build_right_panel())
    splitter.setSizes([220, 520, 520])
    splitter.setStretchFactor(0, 18)
    splitter.setStretchFactor(1, 42)
    splitter.setStretchFactor(2, 40)
    return splitter


def _build_main_central() -> QWidget:
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(_build_top_dataset_selector())
    layout.addWidget(_build_db_status_bar())
    layout.addWidget(_build_main_tabs(), 1)
    layout.addWidget(_build_action_toolbar())
    return central


def main() -> None:
    app = QApplication([])
    window = QMainWindow()
    window.setWindowTitle("Main Window Mockup")
    window.setCentralWidget(_build_main_central())
    window.resize(1360, 820)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
