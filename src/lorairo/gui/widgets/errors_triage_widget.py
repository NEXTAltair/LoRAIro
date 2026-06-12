"""Frame 4 · Errors トリアージ表示ウィジェット。

``ErrorTriageService`` が算出した ``ErrorTriageSummary`` / ``ErrorGroup`` /
``ErrorRow`` を受け取り、サマリ band・フィルタ bar・グループ/個別行表示を
描画する。集約ロジックは持たず表示に専念する (MVC の View)。
アクションは resolve / bulk resolve のみ。
"""

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.error_triage_service import (
    ErrorFilter,
    ErrorGroup,
    ErrorRow,
    ErrorStatusFilter,
    ErrorTriageSummary,
)

# status セグメントの並びと表示ラベル
_STATUS_ORDER: list[tuple[ErrorStatusFilter, str]] = [
    (ErrorStatusFilter.ALL, "すべて"),
    (ErrorStatusFilter.UNRESOLVED, "未解決"),
    (ErrorStatusFilter.RESOLVED, "解決済み"),
]
# combo の「全て」を表す番兵 (None フィルタ)
_ALL_SENTINEL = "__all__"


def _normalize_key(value: str) -> str:
    """objectName 用に記号を ``_`` へ正規化する。"""
    return re.sub(r"[^0-9A-Za-z]+", "_", value)


class ErrorsTriageWidget(QWidget):
    """Frame 4 · Errors トリアージ表示。objectName = "errorsTriageWidget"。"""

    resolve_requested = Signal(int)  # error_id (単一 resolve)
    resolve_group_requested = Signal(list)  # list[int] error_ids (グループ一括 resolve)
    filter_changed = Signal()  # フィルタ/表示モード変更 → controller が再取得
    image_link_clicked = Signal(int)  # image_id (将来 Search 連携用)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorsTriageWidget")

        self._grouped: bool = True
        self._rendered_group_keys: list[tuple[str, str, str | None]] = []
        # bottom bulk 用: 直近 display で表示した全 unresolved_error_id (重複排除・順序保持)
        self._visible_unresolved_ids: list[int] = []

        self._root = QVBoxLayout(self)
        self._build_summary_band()
        self._build_filter_bar()
        self._build_content_area()
        self._build_bulk_bar()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------
    def _build_summary_band(self) -> None:
        """サマリ band (total / unresolved / resolved / last_24h / by_error_type)。"""
        band = QFrame(self)
        band.setObjectName("errorsSummaryBand")
        layout = QHBoxLayout(band)
        self._summary_label = QLabel("", band)
        self._summary_label.setObjectName("errorsSummaryLabel")
        self._summary_by_type_label = QLabel("", band)
        self._summary_by_type_label.setObjectName("errorsSummaryByTypeLabel")
        layout.addWidget(self._summary_label)
        layout.addWidget(self._summary_by_type_label)
        layout.addStretch(1)
        self._root.addWidget(band)

    def _build_filter_bar(self) -> None:
        """フィルタ bar (status セグメント + combo 群 + グループ/個別トグル)。"""
        bar = QFrame(self)
        bar.setObjectName("errorsFilterBar")
        layout = QHBoxLayout(bar)

        # status セグメント (排他ボタン)
        self._status_group = QButtonGroup(self)
        self._status_group.setExclusive(True)
        self._status_buttons: dict[ErrorStatusFilter, QPushButton] = {}
        for status, label in _STATUS_ORDER:
            btn = QPushButton(label, bar)
            btn.setObjectName(f"errorsStatusButton_{status.value}")
            btn.setCheckable(True)
            if status is ErrorStatusFilter.UNRESOLVED:
                btn.setChecked(True)
            self._status_group.addButton(btn)
            self._status_buttons[status] = btn
            btn.clicked.connect(self.filter_changed.emit)
            layout.addWidget(btn)

        # operation / error_type / model combo
        self._operation_combo = self._make_filter_combo(bar, "errorsOperationCombo")
        self._error_type_combo = self._make_filter_combo(bar, "errorsErrorTypeCombo")
        self._model_combo = self._make_filter_combo(bar, "errorsModelCombo")
        layout.addWidget(self._operation_combo)
        layout.addWidget(self._error_type_combo)
        layout.addWidget(self._model_combo)

        # グループ / 個別行トグル
        self._group_toggle = QPushButton("グループ表示", bar)
        self._group_toggle.setObjectName("errorsGroupToggleButton")
        self._group_toggle.setCheckable(True)
        self._group_toggle.setChecked(True)
        self._group_toggle.toggled.connect(self._on_group_toggled)
        layout.addWidget(self._group_toggle)

        layout.addStretch(1)
        self._root.addWidget(bar)

    def _make_filter_combo(self, parent: QWidget, object_name: str) -> QComboBox:
        """「すべて」番兵付きの combo を生成する。"""
        combo = QComboBox(parent)
        combo.setObjectName(object_name)
        combo.addItem("すべて", _ALL_SENTINEL)
        combo.currentIndexChanged.connect(self._on_combo_changed)
        return combo

    def _build_content_area(self) -> None:
        """グループ/個別行を描画する scroll area。"""
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("errorsContentScroll")
        self._scroll.setWidgetResizable(True)
        self._content = QWidget(self._scroll)
        self._content.setObjectName("errorsContent")
        self._content_layout = QVBoxLayout(self._content)
        self._scroll.setWidget(self._content)

        # 空状態 (display で表示制御)
        self._empty_state = QLabel("エラーはありません", self._content)
        self._empty_state.setObjectName("errorsEmptyState")
        self._empty_state.setVisible(False)
        self._content_layout.addWidget(self._empty_state)
        self._content_layout.addStretch(1)

        self._root.addWidget(self._scroll, stretch=1)

    def _build_bulk_bar(self) -> None:
        """bottom の一括 resolve バー。"""
        bar = QFrame(self)
        bar.setObjectName("errorsBulkBar")
        layout = QHBoxLayout(bar)
        layout.addStretch(1)
        self._bulk_button = QPushButton("未解決をすべて resolve", bar)
        self._bulk_button.setObjectName("errorsBulkResolveButton")
        self._bulk_button.clicked.connect(self._on_bulk_resolve)
        layout.addWidget(self._bulk_button)
        self._root.addWidget(bar)

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def display(
        self,
        summary: ErrorTriageSummary,
        groups: list[ErrorGroup],
        rows: list[ErrorRow],
    ) -> None:
        """サマリ band + (グループ表示 or 個別行表示) を再描画する。

        Args:
            summary: 全体サマリ。
            groups: グループ表示用 (``service.group_errors`` の結果)。
            rows: 個別行表示用 (``service.apply_filter`` の結果)。
        """
        self._update_summary(summary)
        self._clear_content()

        # bottom bulk は「表示中の全 unresolved」。グループ表示でもグループの
        # unresolved_error_ids を、個別行表示でも未解決行の error_id を集約する。
        self._visible_unresolved_ids = self._collect_visible_unresolved(groups, rows)

        is_empty = not groups if self._grouped else not rows
        self._empty_state.setVisible(is_empty)
        if is_empty:
            return

        if self._grouped:
            self._render_groups(groups)
        else:
            self._render_rows(rows)

    def _collect_visible_unresolved(self, groups: list[ErrorGroup], rows: list[ErrorRow]) -> list[int]:
        """表示モードに応じた未解決 error_id を重複排除・順序保持で集める。"""
        ids: list[int] = []
        seen: set[int] = set()
        if self._grouped:
            for group in groups:
                for error_id in group.unresolved_error_ids:
                    if error_id not in seen:
                        seen.add(error_id)
                        ids.append(error_id)
        else:
            for row in rows:
                if not row.resolved and row.error_id not in seen:
                    seen.add(row.error_id)
                    ids.append(row.error_id)
        return ids

    def _update_summary(self, summary: ErrorTriageSummary) -> None:
        """サマリ band のラベルを更新する。"""
        self._summary_label.setText(
            f"合計 {summary.total} · 未解決 {summary.unresolved} · "
            f"解決済み {summary.resolved} · 直近24h {summary.last_24h}"
        )
        if summary.by_error_type:
            parts = [f"{name}: {count}" for name, count in summary.by_error_type.items()]
            self._summary_by_type_label.setText(" / ".join(parts))
        else:
            self._summary_by_type_label.setText("")

    def _clear_content(self) -> None:
        """空状態 / stretch を残してコンテンツの動的 widget を破棄する。"""
        keep = {self._empty_state}
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            if item is None:
                continue
            child = item.widget()
            if child is not None and child not in keep:
                self._content_layout.takeAt(i)
                child.setParent(None)
                child.deleteLater()
        self._rendered_group_keys = []

    def _render_groups(self, groups: list[ErrorGroup]) -> None:
        """各 ErrorGroup をカードで描画する。"""
        insert_at = self._content_layout.count() - 1  # stretch の前
        for group in groups:
            card = self._make_group_card(group)
            self._content_layout.insertWidget(insert_at, card)
            insert_at += 1
            self._rendered_group_keys.append((group.operation_type, group.error_type, group.model_name))

    def _make_group_card(self, group: ErrorGroup) -> QFrame:
        """1 グループのカード widget を生成する。"""
        model_label = group.model_name if group.model_name is not None else "(model 無し)"
        model_key = _normalize_key(group.model_name) if group.model_name is not None else "none"

        card = QFrame(self._content)
        card.setObjectName(
            f"errorGroup_{_normalize_key(group.operation_type)}_"
            f"{_normalize_key(group.error_type)}_{model_key}"
        )
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        header = QLabel(f"{group.operation_type} · {group.error_type} · {model_label}", card)
        header.setObjectName("errorGroupHeader")
        layout.addWidget(header)

        badge = QLabel(f"件数 {group.count} · 未解決 {group.unresolved_count}", card)
        layout.addWidget(badge)

        sample = QLabel(group.sample_message, card)
        sample.setWordWrap(True)
        layout.addWidget(sample)

        if group.image_ids:
            images_row = QFrame(card)
            images_layout = QHBoxLayout(images_row)
            images_layout.addWidget(QLabel("影響画像:", images_row))
            for image_id in group.image_ids:
                link = QPushButton(str(image_id), images_row)
                link.setObjectName(f"errorGroupImageLink_{image_id}")
                link.setFlat(True)
                link.clicked.connect(lambda _checked=False, iid=image_id: self.image_link_clicked.emit(iid))
                images_layout.addWidget(link)
            images_layout.addStretch(1)
            layout.addWidget(images_row)

        resolve_btn = QPushButton("このグループを resolve", card)
        resolve_btn.setObjectName("errorGroupResolveButton")
        unresolved_ids = list(group.unresolved_error_ids)
        resolve_btn.clicked.connect(
            lambda _checked=False, ids=unresolved_ids: self.resolve_group_requested.emit(ids)
        )
        resolve_btn.setEnabled(bool(unresolved_ids))
        layout.addWidget(resolve_btn)

        return card

    def _render_rows(self, rows: list[ErrorRow]) -> None:
        """各 ErrorRow を行で描画する。"""
        insert_at = self._content_layout.count() - 1  # stretch の前
        for row in rows:
            line = self._make_row_line(row)
            self._content_layout.insertWidget(insert_at, line)
            insert_at += 1

    def _make_row_line(self, row: ErrorRow) -> QFrame:
        """1 行の widget を生成する。"""
        model_label = row.model_name if row.model_name is not None else "-"

        line = QFrame(self._content)
        line.setObjectName(f"errorRow_{row.error_id}")
        line.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(line)

        info = QLabel(
            f"#{row.error_id} · {row.operation_type} · {row.error_type} · "
            f"{model_label} · {row.error_message}",
            line,
        )
        info.setWordWrap(True)
        layout.addWidget(info, stretch=1)

        if not row.resolved:
            resolve_btn = QPushButton("resolve", line)
            resolve_btn.setObjectName(f"errorRowResolveButton_{row.error_id}")
            error_id = row.error_id
            resolve_btn.clicked.connect(
                lambda _checked=False, eid=error_id: self.resolve_requested.emit(eid)
            )
            layout.addWidget(resolve_btn)
        else:
            layout.addWidget(QLabel("解決済み", line))

        return line

    # ------------------------------------------------------------------
    # アクション
    # ------------------------------------------------------------------
    def _on_group_toggled(self, checked: bool) -> None:
        """グループ/個別行トグルの状態を反映し filter_changed を emit する。"""
        self._grouped = checked
        self._group_toggle.setText("グループ表示" if checked else "個別行表示")
        self.filter_changed.emit()

    def _on_combo_changed(self, _index: int) -> None:
        """combo 変更で filter_changed を emit する。"""
        self.filter_changed.emit()

    def _on_bulk_resolve(self) -> None:
        """表示中の全 unresolved_error_id を集約して emit する。"""
        self.resolve_group_requested.emit(list(self._visible_unresolved_ids))

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def get_filter(self) -> ErrorFilter:
        """フィルタ UI の現在の選択状態を返す。"""
        status = next(
            (s for s, btn in self._status_buttons.items() if btn.isChecked()),
            ErrorStatusFilter.UNRESOLVED,
        )
        return ErrorFilter(
            status=status,
            operation_type=self._combo_value(self._operation_combo),
            error_type=self._combo_value(self._error_type_combo),
            model_name=self._combo_value(self._model_combo),
        )

    def _combo_value(self, combo: QComboBox) -> str | None:
        """combo の現在値を返す (「すべて」番兵は None)。"""
        data = combo.currentData()
        if data == _ALL_SENTINEL:
            return None
        return str(data)

    def is_grouped(self) -> bool:
        """グループ表示モードなら True、個別行モードなら False。"""
        return self._grouped

    def toggle_grouped(self, grouped: bool) -> None:
        """グループ/個別行モードを切り替える (toggle ボタン経由)。"""
        self._group_toggle.setChecked(grouped)

    def _group_keys(self) -> list[tuple[str, str, str | None]]:
        """直近 display で描画したグループのキー順リストを返す (テスト用)。"""
        return list(self._rendered_group_keys)

    def set_filter_options(
        self, operation_types: list[str], error_types: list[str], model_names: list[str]
    ) -> None:
        """フィルタ combo の選択肢を設定する。

        Args:
            operation_types: operation_type の選択肢。
            error_types: error_type の選択肢。
            model_names: model_name の選択肢。
        """
        self._reset_combo(self._operation_combo, operation_types)
        self._reset_combo(self._error_type_combo, error_types)
        self._reset_combo(self._model_combo, model_names)

    def _reset_combo(self, combo: QComboBox, values: list[str]) -> None:
        """combo を「すべて」+ values で再構築する (signal は一時停止)。"""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("すべて", _ALL_SENTINEL)
        for value in values:
            combo.addItem(value, value)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)
