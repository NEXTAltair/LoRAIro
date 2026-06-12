"""Wireframes v11 Frame 2B のステージ別モデルピッカー (Phase 6b)。

ステージ行の「+ 追加」から開き、そのステージに出力を届けられる未選択モデルを
チェック可能リストで提示する。OK 後の `selected_model_ids()` を呼び出し元
(MainWindow) が ModelSelectionWidget のチェック ON に変換する — SSoT は
あくまで「選択モデル集合」であり、本ダイアログは候補提示と選択結果の返却のみ。

Issue #755: API キー未設定の WebAPI モデルも非表示にせず ``○ needs key``
ステータスで可視化する。needs key 行のクリックは ``configure_key_requested``
シグナルで呼び出し元へ通知し、ConfigurationWindow の該当プロバイダ欄へ誘導
する。キー保存後は ``refresh_key_status()`` で ``● API ready`` に解消される。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_per_image_cost,
)
from lorairo.services.model_route_service import required_provider_for
from lorairo.services.pipeline_composition import PipelineStage, StageModelInfo

_EMPTY_CANDIDATES_TEXT = "このステージに追加できる未選択モデルがありません"
_MULTIMODAL_NOTE = "· 1推論で T C S（R は preflight 由来）"

# Issue #755: Wireframes v11 Frame 2B のモデルステータス表現
_STATUS_INSTALLED = "● installed"
_STATUS_API_READY = "● API ready"
_STATUS_NEEDS_KEY = "○ needs key"
_NEEDS_KEY_TOOLTIP = "API キー未設定です。クリックすると設定画面の該当プロバイダ欄を開きます。"

_cost_service = CostEstimationService()


class StageModelPickerDialog(QDialog):
    """ステージに追加可能なモデル候補を列挙するチェックリストダイアログ。

    Signals:
        configure_key_requested (str): ``○ needs key`` 行クリック時に、API キーが
            必要な provider 名 (例 ``"anthropic"``) を通知する (Issue #755)。
    """

    configure_key_requested = Signal(str)

    def __init__(
        self,
        stage: PipelineStage,
        candidates: list[StageModelInfo],
        available_providers: set[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを構築する。

        Args:
            stage: 追加先のパイプラインステージ。
            candidates: このステージに出力を届けられる未選択モデルのリスト。
            available_providers: API キー設定済み provider 集合。None の場合は
                全 provider をキー設定済み扱いにする (後方互換)。
            parent: 親 widget。
        """
        super().__init__(parent)
        self.setWindowTitle(f"{stage.value.upper()} のモデルを選択")

        self._candidates = list(candidates)
        self._available_providers: set[str] | None = (
            set(available_providers) if available_providers is not None else None
        )

        layout = QVBoxLayout(self)

        self._candidate_list = QListWidget(self)
        self._candidate_list.setObjectName("stageModelCandidateList")
        for info in self._candidates:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, info.litellm_model_id)
            self._apply_item_state(item, info)
            self._candidate_list.addItem(item)
        self._candidate_list.itemClicked.connect(self._on_item_clicked)

        if candidates:
            layout.addWidget(self._candidate_list)
        else:
            self._candidate_list.hide()
            empty_label = QLabel(_EMPTY_CANDIDATES_TEXT, self)
            empty_label.setObjectName("emptyCandidatesLabel")
            layout.addWidget(empty_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None and not candidates:
            ok_button.setEnabled(False)
        layout.addWidget(button_box)

    @staticmethod
    def _candidate_text(info: StageModelInfo) -> str:
        """候補 1 件分の表示テキストを返す (Issue #747: コストをカード直載せ)。"""
        origin = f"API: {info.provider}" if info.is_api else "ローカル"
        cost = format_per_image_cost(_cost_service.per_image_usd(info), info.is_api)
        text = f"{info.display_name}（{origin}）· {cost}"
        if info.is_multimodal:
            text += f" {_MULTIMODAL_NOTE}"
        return text

    def _needs_key(self, info: StageModelInfo) -> bool:
        """API キー未設定で実行できない WebAPI モデルか判定する (Issue #755)。"""
        if not info.is_api:
            return False
        if self._available_providers is None:
            return False
        return required_provider_for(info.litellm_model_id, info.provider) not in self._available_providers

    def _status_text(self, info: StageModelInfo) -> str:
        """Wireframes v11 のステータス表現を返す。"""
        if not info.is_api:
            return _STATUS_INSTALLED
        return _STATUS_NEEDS_KEY if self._needs_key(info) else _STATUS_API_READY

    def _apply_item_state(self, item: QListWidgetItem, info: StageModelInfo) -> None:
        """候補行のテキスト・チェック可否・tooltip を現在のキー状況で更新する。

        needs key 行はチェック不可 (実行不能モデルの追加を防ぐ) とし、クリックで
        設定導線を開けることを tooltip で案内する。キー設定済みになった行は
        チェック可能へ戻す。
        """
        item.setText(f"{self._candidate_text(info)} · {self._status_text(info)}")
        if self._needs_key(info):
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(Qt.ItemDataRole.CheckStateRole, None)
            item.setToolTip(_NEEDS_KEY_TOOLTIP)
        else:
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
            )
            if item.data(Qt.ItemDataRole.CheckStateRole) is None:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip("")

    def refresh_key_status(self, available_providers: set[str]) -> None:
        """API キー設定状況を再評価して全行のステータス表示を更新する (Issue #755)。

        キー保存後に呼び出すと ``○ needs key`` 行が ``● API ready`` に変わり、
        チェック可能になる (アプリ再起動不要)。

        Args:
            available_providers: 最新の API キー設定済み provider 集合。
        """
        self._available_providers = set(available_providers)
        for row, info in enumerate(self._candidates):
            item = self._candidate_list.item(row)
            if item is not None:
                self._apply_item_state(item, info)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """needs key 行のクリックで設定導線シグナルを emit する (Issue #755)。"""
        row = self._candidate_list.row(item)
        if not (0 <= row < len(self._candidates)):
            return
        info = self._candidates[row]
        if self._needs_key(info):
            provider = required_provider_for(info.litellm_model_id, info.provider)
            self.configure_key_requested.emit(provider)

    def selected_model_ids(self) -> list[str]:
        """チェック済み候補の litellm_model_id リストを返す。"""
        selected: list[str] = []
        for index in range(self._candidate_list.count()):
            item = self._candidate_list.item(index)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return selected
