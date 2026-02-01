from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))


def _make_placeholder(message: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(message)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return widget


def _make_preview_placeholder() -> QWidget:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Raised)
    layout = QVBoxLayout(frame)
    label = QLabel("Preview (mock)")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    return frame


def _safe_build_widget(builder: Callable[[], QWidget], fallback_label: str) -> QWidget:
    try:
        return builder()
    except Exception as exc:  # mockup用: 個別ウィジェット失敗時も全体表示を継続
        return _make_placeholder(f"{fallback_label}\n{exc}")


def _build_dummy_details():
    from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, ImageDetails

    dummy = AnnotationData(
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
        caption="A mock caption for preview.",
        aesthetic_score=0.732,
        overall_score=780,
        score_type="Aesthetic",
    )
    return ImageDetails(
        image_id=1,
        file_name="mock_image_01.png",
        image_size="1024 x 768",
        file_size="1.25 MB",
        created_date="2026-01-06 10:15:00",
        rating_value="PG-13",
        score_value=780,
        caption=dummy.caption,
        tags="1girl, solo, outdoor",
        annotation_data=dummy,
    )


def _build_selected_image_details_widget() -> QWidget:
    from lorairo.gui.widgets.rating_score_edit_widget import RatingScoreEditWidget
    from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

    details = _build_dummy_details()

    details_widget = SelectedImageDetailsWidget()
    details_widget._update_details_display(details)
    if hasattr(details_widget, "annotation_display"):
        annotation_display = details_widget.annotation_display
        if hasattr(annotation_display, "tableWidgetTags"):
            annotation_display.tableWidgetTags.setVisible(True)
        if hasattr(annotation_display, "_tags_compact_label"):
            annotation_display._tags_compact_label.setVisible(False)
        if hasattr(annotation_display, "_adjust_content_heights"):
            annotation_display._adjust_content_heights()

    edit_widget = RatingScoreEditWidget()
    edit_widget.populate_from_image_data(
        {
            "id": details.image_id,
            "rating": details.rating_value or "PG-13",
            "score": details.score_value,
        }
    )

    summary_layout = getattr(details_widget, "_summary_layout", None)
    target_layout = summary_layout or details_widget.ui.verticalLayoutOverview
    target_layout.removeWidget(details_widget.ui.groupBoxRatingScore)
    details_widget.ui.groupBoxRatingScore.setVisible(False)

    insert_after = target_layout.indexOf(details_widget.ui.annotationDataDisplay)
    if insert_after == -1:
        target_layout.addWidget(edit_widget)
    else:
        target_layout.insertWidget(insert_after + 1, edit_widget)

    for index in range(target_layout.count()):
        target_layout.setStretch(index, 0)
    annotation_index = target_layout.indexOf(details_widget.ui.annotationDataDisplay)
    if annotation_index != -1:
        target_layout.setStretch(annotation_index, 1)

    return details_widget


def _build_rating_score_widget() -> QWidget:
    details = _build_dummy_details()

    container = QWidget()
    layout = QVBoxLayout(container)

    group = QGroupBox("評価・スコア")
    grid = QGridLayout(group)

    label_rating = QLabel("Rating:")
    label_rating_value = QLabel(details.rating_value if details.rating_value else "-")
    label_score = QLabel("スコア:")
    label_score_value = QLabel(str(details.score_value) if details.score_value else "-")

    grid.addWidget(label_rating, 0, 0)
    grid.addWidget(label_rating_value, 0, 1)
    grid.addWidget(label_score, 1, 0)
    grid.addWidget(label_score_value, 1, 1)

    layout.addWidget(group)
    layout.addStretch()
    return container


def _build_batch_tag_widget() -> QWidget:
    from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget

    return BatchTagAddWidget()


def _build_right_panel() -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(5, 5, 5, 5)
    layout.setSpacing(5)

    title = QLabel("プレビュー・詳細")
    title.setStyleSheet("font-weight: bold;")
    layout.addWidget(title)

    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    splitter.addWidget(_make_preview_placeholder())

    tab_widget = QTabWidget()
    tab_widget.addTab(
        _safe_build_widget(_build_selected_image_details_widget, "画像詳細 (mock)"),
        "画像詳細",
    )
    splitter.addWidget(tab_widget)
    splitter.setSizes([550, 450])

    layout.addWidget(splitter)

    layout.setStretch(1, 3)
    return panel


def main() -> None:
    app = QApplication([])
    window = QMainWindow()
    window.setWindowTitle("Right Panel Mockup")
    window.setCentralWidget(_build_right_panel())
    window.resize(520, 820)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
