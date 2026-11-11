"""データセット選択ダイアログ。

画像ディレクトリに加えて、Kohya GUI の設定 JSON (複数可) を選べる。
「Kohya データセットとして取り込む」をオンにすると Kohya データセットの取り込み、オフなら
従来の画像登録として扱う (設定 JSON は任意。Issue #1453)。
Kohya 取り込みでは、`<数字>_<名前>` フォルダごとに取捨・繰り返し回数・トリガーワードを確認して
確定する。トリガーワード候補は横に表示するだけで、採用ボタンを押したときだけ入力欄に入る (Issue #1452)。
従来の画像登録では、画像を直接含むサブフォルダごとに共通タグを入力できる (Issue #1409)。
"""

import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.dataset_import_service import FolderOverride, FolderScanSummary, summarize_folder
from ...services.folder_common_tags import ImageSubfolder, list_image_subfolders, parse_common_tags
from ...services.kohya_scanner import scan_kohya_directory
from ...utils.log import logger
from ..workers.base import LoRAIroWorkerBase
from .ds_no_scroll_combo_box import DsNoScrollComboBox, DsNoScrollSpinBox

# サブフォルダ共通タグ表の列
_FOLDER_COLUMN = 0
_COUNT_COLUMN = 1
_TAGS_COLUMN = 2

# Kohya フォルダ表の列
_K_INCLUDE_COLUMN = 0
_K_FOLDER_COLUMN = 1
_K_REPEATS_COLUMN = 2
_K_IMAGES_COLUMN = 3
_K_NO_TEXT_COLUMN = 4
_K_TRIGGER_COLUMN = 5
_K_CANDIDATE_COLUMN = 6
_K_ADOPT_COLUMN = 7
_K_HEADERS = ("取り込む", "フォルダ", "繰り返し", "画像数", "テキスト無し", "トリガーワード", "候補", "")
_MAX_REPEATS = 9999
_NO_PARENT_VERSION_LABEL = "なし (親の版を指定しない)"
_SCANNING_STATUS_TEXT = "フォルダをスキャン中..."
_SCAN_SHUTDOWN_WAIT_MS = 5000

FolderScanEntry = tuple[str, int, FolderScanSummary]
FolderScanner = Callable[[Path], Sequence[FolderScanEntry]]
SubfolderScanner = Callable[[Path], Sequence[ImageSubfolder]]
ParentVersionEntry = tuple[int, str]
ParentVersionsByDataset = Mapping[str, Sequence[ParentVersionEntry]]
ParentVersionsProvider = Callable[[str], Sequence[ParentVersionEntry]]


@dataclass(frozen=True)
class SubfolderScanResult:
    """サブフォルダ共通タグ表の非同期スキャン結果 (#1546)。"""

    directory: Path
    subfolders: tuple[ImageSubfolder, ...]
    error_text: str = ""


class SubfolderScanWorker(LoRAIroWorkerBase[SubfolderScanResult]):
    """サブフォルダ共通タグ表のスキャンを背景スレッドで行う worker (#1546)。"""

    _OPERATION_TYPE = "subfolder_scan"

    def __init__(
        self,
        directory: Path,
        scanner: SubfolderScanner | None = None,
    ) -> None:
        super().__init__()
        self._directory = directory
        self._scanner = scanner

    def execute(self) -> SubfolderScanResult:
        """対象ディレクトリ内の画像を直接含むサブフォルダを走査して返す。"""
        self._check_cancellation()
        subfolders: tuple[ImageSubfolder, ...] = ()
        error_text = ""
        try:
            if self._scanner is not None:
                raw_entries = self._scanner(self._directory)
            elif "cancel_check" in inspect.signature(list_image_subfolders).parameters:
                raw_entries = list_image_subfolders(self._directory, cancel_check=self._check_cancellation)
            else:
                raw_entries = list_image_subfolders(self._directory)
            collected: list[ImageSubfolder] = []
            for entry in raw_entries:
                self._check_cancellation()
                collected.append(entry)
            subfolders = tuple(collected)
        except OSError as e:
            logger.opt(exception=True).warning(f"サブフォルダのスキャンに失敗: {self._directory}")
            error_text = f"フォルダを読めませんでした: {type(e).__name__}"
        return SubfolderScanResult(
            directory=self._directory,
            subfolders=subfolders,
            error_text=error_text,
        )

    def _should_cancel_completed_result(self) -> bool:
        return False


_ACTIVE_SUBFOLDER_SCAN_RUNNERS: set[tuple[QThread, SubfolderScanWorker]] = set()


@dataclass(frozen=True)
class KohyaFolderScanResult:
    """Kohya フォルダ表の非同期スキャン結果。

    Attributes:
        directory: スキャンしたディレクトリ。
        summaries: `(dir_name, num_repeats, summary)` のタプル列。
        error_text: 読み取り失敗時の表示文。成功時は空文字。
    """

    directory: Path
    summaries: tuple[FolderScanEntry, ...]
    error_text: str = ""


def _scan_kohya_folders(
    directory: Path,
    cancel_check: Callable[[], bool] | None = None,
) -> list[FolderScanEntry]:
    """ディレクトリを Kohya 形式として走査し、フォルダごとの要約を返す。"""
    if not directory.is_dir():
        return []
    entries: list[FolderScanEntry] = []
    for folder in scan_kohya_directory(directory, cancel_check=cancel_check):
        if cancel_check is not None and cancel_check():
            break
        entries.append((folder.dir_name, folder.num_repeats, summarize_folder(folder)))
    return entries


class KohyaFolderScanWorker(LoRAIroWorkerBase[KohyaFolderScanResult]):
    """Kohya フォルダ表のスキャンを背景スレッドで行う worker。"""

    _OPERATION_TYPE = "kohya_folder_scan"

    def __init__(
        self,
        directory: Path,
        scanner: FolderScanner | None = None,
    ) -> None:
        """Worker を初期化する。

        Args:
            directory: スキャン対象ディレクトリ。
            scanner: 差し替え可能なスキャン関数 (テスト用)。`None` なら既定の走査を使う。
        """
        super().__init__()
        self._directory = directory
        self._scanner = scanner

    def execute(self) -> KohyaFolderScanResult:
        """対象ディレクトリをスキャンして要約を返す。"""
        self._check_cancellation()
        summaries: tuple[FolderScanEntry, ...] = ()
        error_text = ""
        try:
            if self._scanner is not None:
                raw_entries = self._scanner(self._directory)
                collected: list[FolderScanEntry] = []
                for entry in raw_entries:
                    self._check_cancellation()
                    collected.append(entry)
                summaries = tuple(collected)
            else:
                summaries = tuple(
                    _scan_kohya_folders(self._directory, cancel_check=self.cancellation.is_canceled)
                )
                self._check_cancellation()
        except OSError as e:
            logger.opt(exception=True).warning(f"Kohya フォルダのスキャンに失敗: {self._directory}")
            error_text = f"フォルダを読めませんでした: {type(e).__name__}"
        return KohyaFolderScanResult(
            directory=self._directory,
            summaries=summaries,
            error_text=error_text,
        )

    def _should_cancel_completed_result(self) -> bool:
        # 世代カウンタ (_scan_generation) で古い結果の破棄をダイアログ側が判定するため、
        # 完了したスキャン結果は常に finished シグナルで通知する。
        return False


# 実行中の (QThread, KohyaFolderScanWorker) を GC から守るモジュールレベル保持
_ACTIVE_SCAN_RUNNERS: set[tuple[QThread, KohyaFolderScanWorker]] = set()


def _normalize_parent_version_entries(
    entries: Sequence[object],
) -> tuple[ParentVersionEntry, ...]:
    """`(version_id, version_name)` または `VersionSummary` 互換オブジェクトの列を正規化する。"""
    normalized: list[ParentVersionEntry] = []
    for entry in entries:
        if isinstance(entry, tuple) and len(entry) == 2:
            vid, vname = entry
            if isinstance(vid, int | str):
                normalized.append((int(vid), str(vname)))
        else:
            vid_attr = getattr(entry, "version_id", None)
            vname_attr = getattr(entry, "version_name", None)
            if isinstance(vid_attr, int) and isinstance(vname_attr, str):
                normalized.append((vid_attr, vname_attr))
    return tuple(normalized)


@dataclass(frozen=True)
class DatasetSelection:
    """データセット選択ダイアログの選択結果。

    Attributes:
        directory: 画像ディレクトリ。
        config_files: 選択された設定 JSON (Kohya 取り込み時のみ。0 個でもよい)。
        dataset_name: データセット名 (Kohya 取り込み時のみ意味を持つ)。
        version_name: 版名。空なら service が候補を作る (Kohya 取り込み時のみ)。
        folder_tags: サブフォルダ (directory からの相対パス) → 共通タグ。
            従来の画像登録時のみ意味を持ち、タグを入力したサブフォルダだけを含む。
        kohya_import: Kohya データセットとして取り込むか (ダイアログのチェックボックス)。
        folder_overrides: Kohya フォルダごとの確定値 (取捨・繰り返し回数・トリガーワード)。
            フォルダ表が選択ディレクトリのものでない場合は `None` (スキャン結果のまま取り込む)。
        parent_version_id: 親の版 ID (Kohya 取り込み時のみ。未指定なら `None`)。
    """

    directory: Path
    config_files: tuple[Path, ...] = ()
    dataset_name: str = ""
    version_name: str = ""
    folder_tags: dict[Path, tuple[str, ...]] = field(default_factory=dict)
    kohya_import: bool = False
    folder_overrides: tuple[FolderOverride, ...] | None = None
    parent_version_id: int | None = None

    @property
    def is_kohya_import(self) -> bool:
        """Kohya 取り込みとして扱うか。設定 JSON の有無とは独立に、チェックボックスで決まる。"""
        return self.kohya_import


class DatasetSelectDialog(QDialog):
    """画像ディレクトリと設定 JSON を選ぶモーダルダイアログ。"""

    # worker スレッドから GUI スレッドへスキャン結果を渡す内部シグナル
    _kohya_scan_completed = Signal(int, object)
    _kohya_scan_failed = Signal(int, object, str)
    _subfolder_scan_completed = Signal(int, object)
    _subfolder_scan_failed = Signal(int, object, str)
    # テストや外部からスキャン完了を監視できる公開シグナル (世代番号)
    kohya_scan_finished = Signal(int)
    subfolder_scan_finished = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        parent_versions_by_dataset: ParentVersionsByDataset | Sequence[ParentVersionEntry] | None = None,
        *,
        parent_versions_provider: ParentVersionsProvider | None = None,
        folder_scanner: FolderScanner | None = None,
        subfolder_scanner: SubfolderScanner | None = None,
    ) -> None:
        """ダイアログを初期化する。

        Args:
            parent: 親ウィジェット。
            parent_versions_by_dataset: データセット名 → 親の版候補 `(version_id, version_name)` の辞書
                (または現在のデータセットに対する `(version_id, version_name)` の列)。
                ダイアログは DB に直接触れず、外から渡された一覧を表示する。
            parent_versions_provider: データセット名を受け取り `(version_id, version_name)` の列を返す関数。
            folder_scanner: Kohya フォルダ走査関数 (テストでの差し替え用)。
            subfolder_scanner: サブフォルダ走査関数 (テストでの差し替え用)。
        """
        super().__init__(parent)
        self.setWindowTitle("データセットを選択")
        self.setMinimumWidth(520)
        self.setModal(True)
        # ディレクトリ名から自動入力した直近のデータセット名 (手入力を上書きしないため)
        self._auto_dataset_name = ""
        # サブフォルダ表を作った時点のディレクトリ (同じなら作り直さず入力を保つ)
        self._scanned_directory: Path | None = None
        self._subfolder_error_text = ""
        self._subfolder_scan_generation = 0
        self._scanning_subfolders = False
        self._scanning_subfolder_directory: Path | None = None
        self._subfolder_scan_runners: dict[int, tuple[QThread, SubfolderScanWorker]] = {}
        self._subfolder_scanner = subfolder_scanner
        # Kohya フォルダ表を作った時点のディレクトリ (同じなら作り直さず入力を保つ)
        self._kohya_scanned_directory: Path | None = None
        # Kohya フォルダのスキャンに失敗したときの表示文
        self._kohya_error_text = ""
        # 非同期 Kohya フォルダスキャンの世代管理と状態
        self._scan_generation = 0
        self._scanning_kohya = False
        self._scanning_directory: Path | None = None
        self._scan_runners: dict[int, tuple[QThread, KohyaFolderScanWorker]] = {}
        self._folder_scanner = folder_scanner
        # 親の版候補 (DB 非依存で外から受け取る)
        self._parent_versions_by_dataset: dict[str, tuple[ParentVersionEntry, ...]] = {}
        self._direct_parent_versions: tuple[ParentVersionEntry, ...] | None = None
        self._parent_versions_provider = parent_versions_provider
        self._combo_dataset_name: str | None = None
        self._combo_versions: tuple[ParentVersionEntry, ...] = ()

        self._kohya_scan_completed.connect(self._on_kohya_scan_finished)
        self._kohya_scan_failed.connect(self._on_kohya_scan_error)
        self._subfolder_scan_completed.connect(self._on_subfolder_scan_finished)
        self._subfolder_scan_failed.connect(self._on_subfolder_scan_error)
        self._setup_ui()
        if parent_versions_by_dataset is not None:
            self.set_available_parent_versions(parent_versions_by_dataset)
        else:
            self._refresh_parent_version_combo()
        self._update_state()

    def _setup_ui(self) -> None:
        """UI を構築する。"""
        layout = QVBoxLayout(self)

        # ディレクトリ欄
        layout.addWidget(QLabel("画像ディレクトリ"))
        dir_row = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("画像ディレクトリを選択")
        self.directory_edit.textChanged.connect(self._on_directory_changed)
        # 走査はキー入力ごとでなく、入力確定時と参照ボタン選択時に非同期で行う (#1546)
        self.directory_edit.editingFinished.connect(self.refresh_subfolders_async)
        self.browse_button = QPushButton("参照...")
        self.browse_button.setToolTip("画像ディレクトリを選択")
        self.browse_button.clicked.connect(self._browse_directory)
        dir_row.addWidget(self.directory_edit)
        dir_row.addWidget(self.browse_button)
        layout.addLayout(dir_row)

        # Kohya 取り込みの切り替え (設定 JSON の有無とは独立。Issue #1453)
        self.kohya_check = QCheckBox("Kohya データセットとして取り込む (<数字>_<名前> フォルダ単位)")
        self.kohya_check.toggled.connect(self._on_kohya_toggled)
        layout.addWidget(self.kohya_check)

        # 設定 JSON 一覧
        self.config_label = QLabel(
            "Kohya 設定 JSON (任意。版に学習設定として保存します。追加すると Kohya 取り込みになります)"
        )
        layout.addWidget(self.config_label)
        self.config_list = QListWidget()
        self.config_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.config_list.model().rowsInserted.connect(self._update_state)
        self.config_list.model().rowsRemoved.connect(self._update_state)
        self.config_list.itemSelectionChanged.connect(self._update_state)
        layout.addWidget(self.config_list)
        config_buttons = QHBoxLayout()
        self.add_config_button = QPushButton("追加...")
        self.add_config_button.setToolTip("Kohya 設定 JSON ファイルを追加")
        self.add_config_button.clicked.connect(self._add_configs)
        self.remove_config_button = QPushButton("削除")
        self.remove_config_button.setToolTip("選択中の設定 JSON を一覧から削除")
        self.remove_config_button.clicked.connect(self._remove_selected_configs)
        config_buttons.addWidget(self.add_config_button)
        config_buttons.addWidget(self.remove_config_button)
        config_buttons.addStretch()
        layout.addLayout(config_buttons)

        # データセット名 / 版名 / 親の版
        form = QFormLayout()
        self.dataset_name_edit = QLineEdit()
        self.dataset_name_edit.textChanged.connect(self._on_dataset_name_changed)
        self.version_name_edit = QLineEdit()
        self.version_name_edit.setPlaceholderText("空なら設定 JSON の output_name かフォルダ名から決定")
        self.parent_version_combo: QComboBox = DsNoScrollComboBox()
        form.addRow("データセット名", self.dataset_name_edit)
        form.addRow("版名", self.version_name_edit)
        form.addRow("親の版", self.parent_version_combo)
        layout.addLayout(form)

        # Kohya フォルダ表 (Kohya 取り込みのみ)
        self._setup_kohya_table(layout)

        # サブフォルダごとの共通タグ (従来の画像登録のみ)
        self.folder_tags_label = QLabel(
            "サブフォルダごとの共通タグ (任意。カンマ区切り。入力した表記のまま手動タグとして付きます)"
        )
        self.folder_tags_label.setWordWrap(True)
        layout.addWidget(self.folder_tags_label)
        self.folder_table = QTableWidget(0, 3)
        self.folder_table.setHorizontalHeaderLabels(["サブフォルダ", "画像数", "共通タグ"])
        self.folder_table.verticalHeader().setVisible(False)
        self.folder_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.folder_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.folder_table.horizontalHeader()
        header.setSectionResizeMode(_FOLDER_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COUNT_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_TAGS_COLUMN, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.folder_table)
        self.folder_empty_label = QLabel("画像を含むサブフォルダはありません")
        layout.addWidget(self.folder_empty_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _setup_kohya_table(self, layout: QVBoxLayout) -> None:
        """Kohya フォルダ表 (取捨・繰り返し回数・トリガーワード・候補) を作る。"""
        self.kohya_label = QLabel(
            "取り込むフォルダ (トリガーワード候補は確定値ではありません。採用を押すと入力欄に入ります)"
        )
        self.kohya_label.setWordWrap(True)
        layout.addWidget(self.kohya_label)
        self.kohya_table = QTableWidget(0, len(_K_HEADERS))
        self.kohya_table.setHorizontalHeaderLabels(list(_K_HEADERS))
        self.kohya_table.verticalHeader().setVisible(False)
        self.kohya_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.kohya_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.kohya_table.horizontalHeader()
        for column in range(len(_K_HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_K_TRIGGER_COLUMN, QHeaderView.ResizeMode.Stretch)
        self.kohya_table.itemChanged.connect(self._update_state)
        layout.addWidget(self.kohya_table)
        self.kohya_summary_label = QLabel("")
        self.kohya_summary_label.setWordWrap(True)
        layout.addWidget(self.kohya_summary_label)

    # --- 親の版 ---

    def set_available_parent_versions(
        self,
        versions: ParentVersionsByDataset | Sequence[object],
    ) -> None:
        """外で取得した親の版の候補を設定し、コンボボックスを更新する。

        Args:
            versions: データセット名 → `(version_id, version_name)` 列の辞書、
                `VersionSummary` 互換オブジェクトの列、または `(version_id, version_name)` の列。
        """
        if isinstance(versions, Mapping):
            self._parent_versions_by_dataset = {
                str(dataset_name): _normalize_parent_version_entries(entries)
                for dataset_name, entries in versions.items()
            }
            self._direct_parent_versions = None
        else:
            entries_list = list(versions)
            if entries_list and all(
                hasattr(item, "dataset_name")
                and hasattr(item, "version_id")
                and hasattr(item, "version_name")
                for item in entries_list
            ):
                grouped: dict[str, list[ParentVersionEntry]] = {}
                for item in entries_list:
                    ds_name = str(getattr(item, "dataset_name", ""))
                    v_id = int(getattr(item, "version_id", 0))
                    v_name = str(getattr(item, "version_name", ""))
                    grouped.setdefault(ds_name, []).append((v_id, v_name))
                self._parent_versions_by_dataset = {k: tuple(v) for k, v in grouped.items()}
                self._direct_parent_versions = None
            else:
                self._parent_versions_by_dataset = {}
                self._direct_parent_versions = _normalize_parent_version_entries(entries_list)
        self._combo_dataset_name = None
        self._refresh_parent_version_combo(preserve_selection=True)

    def _resolve_parent_versions(self, dataset_name: str) -> tuple[ParentVersionEntry, ...]:
        """データセット名に対する親の版の候補を返す。"""
        if self._parent_versions_provider is not None:
            if not dataset_name:
                return ()
            return _normalize_parent_version_entries(self._parent_versions_provider(dataset_name))
        if dataset_name in self._parent_versions_by_dataset:
            return self._parent_versions_by_dataset[dataset_name]
        if self._direct_parent_versions is not None and not self._parent_versions_by_dataset:
            return self._direct_parent_versions
        return ()

    def _refresh_parent_version_combo(self, *, preserve_selection: bool = False) -> None:
        """現在のデータセット名に対応する親の版の候補でコンボボックスを更新する。"""
        dataset_name = self.dataset_name_edit.text().strip()
        versions = self._resolve_parent_versions(dataset_name)
        if (
            not preserve_selection
            and dataset_name == self._combo_dataset_name
            and versions == self._combo_versions
        ):
            return
        previous_id = (
            self.selected_parent_version_id()
            if (preserve_selection or dataset_name == self._combo_dataset_name)
            else None
        )
        self._combo_dataset_name = dataset_name
        self._combo_versions = versions

        self.parent_version_combo.blockSignals(True)
        try:
            self.parent_version_combo.clear()
            self.parent_version_combo.addItem(_NO_PARENT_VERSION_LABEL, None)
            selected_index = 0
            for index, (version_id, version_name) in enumerate(versions, start=1):
                label = f"{version_name} (#{version_id})" if version_name else f"#{version_id}"
                self.parent_version_combo.addItem(label, int(version_id))
                if previous_id is not None and int(version_id) == previous_id:
                    selected_index = index
            self.parent_version_combo.setCurrentIndex(selected_index)
        finally:
            self.parent_version_combo.blockSignals(False)

    def selected_parent_version_id(self) -> int | None:
        """選択中の親の版 ID を返す (「なし」なら None)。"""
        data = self.parent_version_combo.currentData()
        return int(data) if isinstance(data, int) else None

    def set_selected_parent_version_id(self, version_id: int | None) -> bool:
        """親の版 ID を選択する。選択肢にあれば True を返す。"""
        index = self.parent_version_combo.findData(version_id)
        if index < 0:
            return False
        self.parent_version_combo.setCurrentIndex(index)
        return True

    # --- 操作 ---

    @property
    def is_scanning_kohya(self) -> bool:
        """Kohya フォルダ表の非同期スキャンが進行中か。"""
        return self._scanning_kohya

    @property
    def is_scanning_subfolders(self) -> bool:
        """サブフォルダ共通タグ表の非同期スキャンが進行中か (#1546)。"""
        return self._scanning_subfolders

    def _browse_directory(self) -> None:
        """ディレクトリ選択ダイアログを開き、非同期でサブフォルダを走査する (#1546)。"""
        directory = QFileDialog.getExistingDirectory(
            self, "データセットディレクトリを選択してください", "", QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.directory_edit.setText(directory)
            self.refresh_subfolders_async()

    def _add_configs(self) -> None:
        """設定 JSON の選択ダイアログを開き、一覧へ追加する。"""
        files, _ = QFileDialog.getOpenFileNames(self, "設定 JSON を選択", "", "JSON (*.json)")
        for file in files:
            self.add_config_file(Path(file))

    def add_config_file(self, path: Path) -> None:
        """設定 JSON を一覧へ追加する (重複は無視)。

        Args:
            path: 追加する設定 JSON のパス。
        """
        text = str(path)
        existing = {self.config_list.item(i).text() for i in range(self.config_list.count())}
        if text not in existing:
            self.config_list.addItem(text)
        # 設定 JSON は Kohya 取り込みでのみ使うため、追加したら Kohya 取り込みに切り替える
        self.kohya_check.setChecked(True)

    def _remove_selected_configs(self) -> None:
        """一覧で選択中の設定 JSON を取り除く。"""
        for item in self.config_list.selectedItems():
            self.config_list.takeItem(self.config_list.row(item))

    def _on_dataset_name_changed(self, _text: str) -> None:
        """データセット名変更時、親の版の候補と画面状態を更新する。"""
        self._refresh_parent_version_combo()
        self._update_state()

    def _on_directory_changed(self, text: str) -> None:
        """ディレクトリ変更時、データセット名が未編集ならディレクトリ名を既定にする。"""
        current = self.dataset_name_edit.text()
        if current == "" or current == self._auto_dataset_name:
            self._auto_dataset_name = Path(text).name if text.strip() else ""
            self.dataset_name_edit.setText(self._auto_dataset_name)
        new_directory = self._current_directory()
        if self._scanning_kohya and new_directory != self._scanning_directory:
            # スキャン中にルートが変わったら世代を進め、進行中の古いスキャン結果を破棄する
            self._scan_generation += 1
            self._scanning_kohya = False
            self._scanning_directory = None
        if self._scanning_subfolders and new_directory != self._scanning_subfolder_directory:
            self._subfolder_scan_generation += 1
            self._scanning_subfolders = False
            self._scanning_subfolder_directory = None
        self._update_state()

    def _on_kohya_toggled(self, checked: bool) -> None:
        """Kohya 取り込みの切り替え時にフォルダ表を非同期更新する (#1546)。"""
        if checked:
            if self._scanning_subfolders or self._subfolder_scan_runners:
                self._subfolder_scan_generation += 1
                self._scanning_subfolders = False
                self._scanning_subfolder_directory = None
                for _old_gen, (_old_thread, old_sub_worker) in list(self._subfolder_scan_runners.items()):
                    old_sub_worker.cancel()
            self.refresh_kohya_folders()
        else:
            if self._scanning_kohya or self._scan_runners:
                self._scan_generation += 1
                self._scanning_kohya = False
                self._scanning_directory = None
                for _old_gen, (_old_thread, old_kohya_worker) in list(self._scan_runners.items()):
                    old_kohya_worker.cancel()
            directory = self._current_directory()
            if directory is not None and directory != self._scanned_directory:
                self.refresh_subfolders_async()
        self._update_state()

    _on_kohya_mode_toggled = _on_kohya_toggled

    def _current_directory(self) -> Path | None:
        text = self.directory_edit.text().strip()
        return Path(text) if text else None

    def _populate_folder_table(self, subfolders: Sequence[ImageSubfolder]) -> None:
        """サブフォルダ共通タグ表を指定のサブフォルダ一覧で構築する。"""
        self.folder_table.setRowCount(len(subfolders))
        read_only = Qt.ItemFlag.ItemIsEnabled
        for row, subfolder in enumerate(subfolders):
            folder_item = QTableWidgetItem(subfolder.relative_path.as_posix())
            folder_item.setFlags(read_only)
            count_item = QTableWidgetItem(str(subfolder.image_count))
            count_item.setFlags(read_only)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.folder_table.setItem(row, _FOLDER_COLUMN, folder_item)
            self.folder_table.setItem(row, _COUNT_COLUMN, count_item)
            self.folder_table.setItem(row, _TAGS_COLUMN, QTableWidgetItem(""))

    def refresh_subfolders(self) -> None:
        """入力中のディレクトリを走査し、サブフォルダ共通タグ表 (と Kohya フォルダ表) を作り直す。

        同じディレクトリなら作り直さず、入力済みのタグを保つ。Kohya フォルダ表は Kohya 取り込みが
        オンのときだけ作る。単体テスト互換性のため本メソッドの直接呼び出しは同期走査を維持する (#1546)。
        """
        if self.kohya_check.isChecked():
            self.refresh_kohya_folders()
        directory = self._current_directory()
        if not self._scanning_subfolders and directory == self._scanned_directory:
            return
        if self._scanning_subfolders or self._subfolder_scan_runners:
            self._subfolder_scan_generation += 1
            self._scanning_subfolders = False
            self._scanning_subfolder_directory = None
            for _old_gen, (_old_thread, old_worker) in list(self._subfolder_scan_runners.items()):
                old_worker.cancel()
        self._scanned_directory = directory
        self._subfolder_error_text = ""
        if directory is None:
            subfolders: Sequence[ImageSubfolder] = ()
        elif self._subfolder_scanner is not None:
            subfolders = self._subfolder_scanner(directory)
        else:
            subfolders = list_image_subfolders(directory)
        self._populate_folder_table(subfolders)
        self._update_state()

    def refresh_subfolders_async(self) -> None:
        """入力中のディレクトリを非同期スキャンし、サブフォルダ共通タグ表を作り直す (#1546)。"""
        if self.kohya_check.isChecked():
            self.refresh_kohya_folders()
            return
        directory = self._current_directory()
        if not self._scanning_subfolders and directory == self._scanned_directory:
            return
        if self._scanning_subfolders and directory == self._scanning_subfolder_directory:
            return

        self._subfolder_scan_generation += 1
        generation = self._subfolder_scan_generation
        for _old_gen, (_old_thread, old_worker) in list(self._subfolder_scan_runners.items()):
            old_worker.cancel()
        self._scanned_directory = None
        self._subfolder_error_text = ""
        self.folder_table.setRowCount(0)

        if directory is None:
            self._scanning_subfolders = False
            self._scanning_subfolder_directory = None
            self._update_state()
            return

        self._scanning_subfolders = True
        self._scanning_subfolder_directory = directory
        self._update_state()
        self._start_subfolder_scan_worker(generation, directory)

    def _start_subfolder_scan_worker(self, generation: int, directory: Path) -> None:
        """専用 QThread で SubfolderScanWorker を起動する (#1546)。"""
        thread = QThread()
        worker = SubfolderScanWorker(directory, scanner=self._subfolder_scanner)
        worker.moveToThread(thread)
        runner = (thread, worker)
        _ACTIVE_SUBFOLDER_SCAN_RUNNERS.add(runner)
        self._subfolder_scan_runners[generation] = runner

        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda result, gen=generation: self._subfolder_scan_completed.emit(gen, result)
        )
        worker.error_occurred.connect(
            lambda message, gen=generation, d=directory: self._subfolder_scan_failed.emit(
                gen, d, str(message)
            )
        )
        worker.finished.connect(thread.quit)
        worker.error_occurred.connect(thread.quit)
        worker.canceled.connect(thread.quit)
        thread.finished.connect(
            lambda gen=generation, r=runner: self._on_subfolder_scan_thread_finished(gen, r)
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_subfolder_scan_thread_finished(
        self, generation: int, runner: tuple[QThread, SubfolderScanWorker]
    ) -> None:
        """サブフォルダスキャン用 QThread の終了時に GUI スレッドで参照を解放する (#1546)。"""
        self._subfolder_scan_runners.pop(generation, None)
        _ACTIVE_SUBFOLDER_SCAN_RUNNERS.discard(runner)

    @Slot(int, object)
    def _on_subfolder_scan_finished(self, generation: int, result: object) -> None:
        """非同期サブフォルダスキャン完了時に最新世代の結果だけを表へ反映する (#1546)。"""
        if generation != self._subfolder_scan_generation or not isinstance(result, SubfolderScanResult):
            return
        if result.directory != self._current_directory():
            return

        self._scanning_subfolders = False
        self._scanning_subfolder_directory = None
        self._scanned_directory = result.directory
        self._subfolder_error_text = result.error_text
        self._populate_folder_table(result.subfolders)
        self._update_state()
        self.subfolder_scan_finished.emit(generation)

    @Slot(int, object, str)
    def _on_subfolder_scan_error(self, generation: int, directory: object, message: str) -> None:
        """非同期サブフォルダスキャンの予期しない失敗を最新世代に限り反映する (#1546)。"""
        if generation != self._subfolder_scan_generation:
            return
        self._scanning_subfolders = False
        self._scanning_subfolder_directory = None
        self._scanned_directory = directory if isinstance(directory, Path) else None
        self._subfolder_error_text = f"フォルダを読めませんでした: {message}"
        self._update_state()
        self.subfolder_scan_finished.emit(generation)

    def refresh_kohya_folders(self) -> None:
        """入力中のディレクトリを Kohya 形式として非同期スキャンし、フォルダ表を作り直す。

        同じディレクトリなら作り直さず、入力済みの値を保つ。トリガーワード欄は空のままにし、
        候補は「候補」列に表示するだけにする (確認なしに確定しない。ADR 0098)。
        """
        directory = self._current_directory()
        if not self._scanning_kohya and directory == self._kohya_scanned_directory:
            return
        if self._scanning_kohya and directory == self._scanning_directory:
            return

        self._scan_generation += 1
        generation = self._scan_generation
        for _old_gen, (_old_thread, old_worker) in list(self._scan_runners.items()):
            old_worker.cancel()
        self._kohya_scanned_directory = None
        self._kohya_error_text = ""

        self.kohya_table.blockSignals(True)
        try:
            self.kohya_table.setRowCount(0)
        finally:
            self.kohya_table.blockSignals(False)

        if directory is None:
            self._scanning_kohya = False
            self._scanning_directory = None
            self._update_state()
            return

        self._scanning_kohya = True
        self._scanning_directory = directory
        self._update_state()
        self._start_kohya_scan_worker(generation, directory)

    def _start_kohya_scan_worker(self, generation: int, directory: Path) -> None:
        """専用 QThread で KohyaFolderScanWorker を起動する。"""
        thread = QThread()
        worker = KohyaFolderScanWorker(directory, scanner=self._folder_scanner)
        worker.moveToThread(thread)
        runner = (thread, worker)
        _ACTIVE_SCAN_RUNNERS.add(runner)
        self._scan_runners[generation] = runner

        thread.started.connect(worker.run)
        worker.finished.connect(lambda result, gen=generation: self._kohya_scan_completed.emit(gen, result))
        worker.error_occurred.connect(
            lambda message, gen=generation, d=directory: self._kohya_scan_failed.emit(gen, d, str(message))
        )
        worker.finished.connect(thread.quit)
        worker.error_occurred.connect(thread.quit)
        worker.canceled.connect(thread.quit)
        # worker.deleteLater は worker スレッドで繋がない (GIL / signal-slot mutex の ABBA デッドロック防止)。
        # thread.finished で GUI スレッド側の参照を切ることで安全に破棄する。
        thread.finished.connect(lambda gen=generation, r=runner: self._on_scan_thread_finished(gen, r))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_scan_thread_finished(
        self, generation: int, runner: tuple[QThread, KohyaFolderScanWorker]
    ) -> None:
        """スキャン用 QThread の終了時に GUI スレッドで参照を解放する。"""
        self._scan_runners.pop(generation, None)
        _ACTIVE_SCAN_RUNNERS.discard(runner)

    @Slot(int, object)
    def _on_kohya_scan_finished(self, generation: int, result: object) -> None:
        """非同期スキャン完了時に最新世代の結果だけをフォルダ表へ反映する。"""
        if generation != self._scan_generation or not isinstance(result, KohyaFolderScanResult):
            return
        if result.directory != self._current_directory():
            return

        self._scanning_kohya = False
        self._scanning_directory = None
        self._kohya_scanned_directory = result.directory
        self._kohya_error_text = result.error_text

        self.kohya_table.blockSignals(True)
        try:
            self.kohya_table.setRowCount(0)
            self.kohya_table.setRowCount(len(result.summaries))
            for row, (dir_name, num_repeats, summary) in enumerate(result.summaries):
                self._fill_kohya_row(row, dir_name, num_repeats, summary)
        finally:
            self.kohya_table.blockSignals(False)
        self._update_state()
        self.kohya_scan_finished.emit(generation)

    @Slot(int, object, str)
    def _on_kohya_scan_error(self, generation: int, directory: object, message: str) -> None:
        """非同期スキャンの予期しない失敗を最新世代に限り反映する。"""
        if generation != self._scan_generation:
            return
        self._scanning_kohya = False
        self._scanning_directory = None
        self._kohya_scanned_directory = directory if isinstance(directory, Path) else None
        self._kohya_error_text = f"フォルダを読めませんでした: {message}"
        self._update_state()
        self.kohya_scan_finished.emit(generation)

    def wait_for_scan(self, timeout_ms: int = _SCAN_SHUTDOWN_WAIT_MS) -> bool:
        """進行中のフォルダスキャン (Kohya / サブフォルダ) が終わるまでイベントを処理して待つ。

        Args:
            timeout_ms: 最大待機ミリ秒。

        Returns:
            スキャンが完了していれば True。
        """
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while (self._scanning_kohya or self._scanning_subfolders) and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.005)
        QCoreApplication.processEvents()
        return not (self._scanning_kohya or self._scanning_subfolders)

    def _stop_scan_workers(self) -> None:
        """実行中のフォルダスキャン worker スレッドへ協調キャンセルを送り、共通デッドライン内で待機する。"""
        if self._scanning_kohya or self._scan_runners:
            self._scan_generation += 1
        self._scanning_kohya = False
        self._scanning_directory = None
        if self._scanning_subfolders or self._subfolder_scan_runners:
            self._subfolder_scan_generation += 1
        self._scanning_subfolders = False
        self._scanning_subfolder_directory = None

        runners = list(self._scan_runners.items())
        subfolder_runners = list(self._subfolder_scan_runners.items())
        for _generation, (thread, kohya_worker) in runners:
            kohya_worker.cancel()
            thread.quit()
        for _generation, (thread, sub_worker) in subfolder_runners:
            sub_worker.cancel()
            thread.quit()

        deadline = time.monotonic() + (_SCAN_SHUTDOWN_WAIT_MS / 1000.0)
        for generation, runner in runners:
            thread, _kohya_worker = runner
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if thread.wait(remaining_ms):
                self._scan_runners.pop(generation, None)
                _ACTIVE_SCAN_RUNNERS.discard(runner)
            else:
                logger.warning(
                    f"Kohya フォルダスキャン worker が時間内に停止しませんでした (gen={generation})"
                )
        for generation, sub_runner in subfolder_runners:
            thread, _sub_worker = sub_runner
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if thread.wait(remaining_ms):
                self._subfolder_scan_runners.pop(generation, None)
                _ACTIVE_SUBFOLDER_SCAN_RUNNERS.discard(sub_runner)
            else:
                logger.warning(
                    f"サブフォルダスキャン worker が時間内に停止しませんでした (gen={generation})"
                )

    def _fill_kohya_row(
        self, row: int, dir_name: str, num_repeats: int, summary: FolderScanSummary
    ) -> None:
        """Kohya フォルダ表の 1 行を作る。"""
        read_only = Qt.ItemFlag.ItemIsEnabled
        include_item = QTableWidgetItem("")
        include_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        include_item.setCheckState(Qt.CheckState.Checked)
        self.kohya_table.setItem(row, _K_INCLUDE_COLUMN, include_item)

        folder_item = QTableWidgetItem(dir_name)
        folder_item.setFlags(read_only)
        self.kohya_table.setItem(row, _K_FOLDER_COLUMN, folder_item)

        repeats = DsNoScrollSpinBox()
        repeats.setRange(1, _MAX_REPEATS)
        repeats.setValue(max(1, min(num_repeats, _MAX_REPEATS)))
        self.kohya_table.setCellWidget(row, _K_REPEATS_COLUMN, repeats)

        for column, value in (
            (_K_IMAGES_COLUMN, summary.image_count),
            (_K_NO_TEXT_COLUMN, summary.images_without_text),
        ):
            count_item = QTableWidgetItem(str(value))
            count_item.setFlags(read_only)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.kohya_table.setItem(row, column, count_item)

        # トリガーワードは空で始める (候補を初期値にしない)
        self.kohya_table.setItem(row, _K_TRIGGER_COLUMN, QTableWidgetItem(""))

        candidate = summary.trigger_candidate
        candidate_text = f"{candidate} ({summary.trigger_match_rate:.0%})" if candidate else "-"
        candidate_item = QTableWidgetItem(candidate_text)
        candidate_item.setFlags(read_only)
        self.kohya_table.setItem(row, _K_CANDIDATE_COLUMN, candidate_item)

        adopt = QPushButton("採用")
        adopt.setToolTip("トリガーワード候補を入力欄に採用")
        adopt.setEnabled(candidate is not None)
        if candidate is not None:
            adopt.clicked.connect(lambda _checked=False, r=row, word=candidate: self.adopt_trigger(r, word))
        self.kohya_table.setCellWidget(row, _K_ADOPT_COLUMN, adopt)

    def adopt_trigger(self, row: int, word: str) -> None:
        """トリガーワード候補を、その行の入力欄に入れる。

        Args:
            row: Kohya フォルダ表の行。
            word: 入れるトリガーワード。
        """
        item = self.kohya_table.item(row, _K_TRIGGER_COLUMN)
        if item is not None:
            item.setText(word)

    def kohya_row(self, dir_name: str) -> int | None:
        """Kohya フォルダ表で `dir_name` の行番号を返す。無ければ None。

        Args:
            dir_name: フォルダ名 (`10_name` 形式)。
        """
        for row in range(self.kohya_table.rowCount()):
            item = self.kohya_table.item(row, _K_FOLDER_COLUMN)
            if item is not None and item.text() == dir_name:
                return row
        return None

    def _repeats_spin(self, row: int) -> QSpinBox | None:
        widget = self.kohya_table.cellWidget(row, _K_REPEATS_COLUMN)
        return widget if isinstance(widget, QSpinBox) else None

    def _collect_folder_overrides(self) -> tuple[FolderOverride, ...]:
        """Kohya フォルダ表の値を確定値として集める。"""
        overrides: list[FolderOverride] = []
        for row in range(self.kohya_table.rowCount()):
            folder_item = self.kohya_table.item(row, _K_FOLDER_COLUMN)
            include_item = self.kohya_table.item(row, _K_INCLUDE_COLUMN)
            trigger_item = self.kohya_table.item(row, _K_TRIGGER_COLUMN)
            spin = self._repeats_spin(row)
            if folder_item is None or include_item is None or spin is None:
                continue
            trigger = trigger_item.text().strip() if trigger_item is not None else ""
            overrides.append(
                FolderOverride(
                    dir_name=folder_item.text(),
                    include=include_item.checkState() == Qt.CheckState.Checked,
                    num_repeats=spin.value(),
                    trigger_word=trigger or None,
                )
            )
        return tuple(overrides)

    def _kohya_table_is_current(self) -> bool:
        """Kohya フォルダ表が、入力中のディレクトリをスキャン完了したものか。"""
        directory = self._current_directory()
        return (
            not self._scanning_kohya
            and directory is not None
            and directory == self._kohya_scanned_directory
        )

    def set_folder_tags_text(self, relative_path: Path, text: str) -> bool:
        """サブフォルダの共通タグ欄へ文字列を入れる。

        Args:
            relative_path: 選択ディレクトリからの相対パス。
            text: カンマ区切りのタグ文字列。

        Returns:
            該当するサブフォルダの行があれば True。
        """
        for row in range(self.folder_table.rowCount()):
            tags_item = self.folder_table.item(row, _TAGS_COLUMN)
            if tags_item is not None and Path(self._cell_text(row, _FOLDER_COLUMN)) == relative_path:
                tags_item.setText(text)
                return True
        return False

    def _cell_text(self, row: int, column: int) -> str:
        """サブフォルダ表のセル文字列を返す (セルが無ければ空文字)。"""
        item = self.folder_table.item(row, column)
        return item.text() if item is not None else ""

    def _collect_folder_tags(self) -> dict[Path, tuple[str, ...]]:
        """共通タグを入力したサブフォルダだけを集める。"""
        folder_tags: dict[Path, tuple[str, ...]] = {}
        for row in range(self.folder_table.rowCount()):
            tags = parse_common_tags(self._cell_text(row, _TAGS_COLUMN))
            if tags:
                folder_tags[Path(self._cell_text(row, _FOLDER_COLUMN))] = tags
        return folder_tags

    def _update_state(self, *_args: object) -> None:
        """入力状態に応じて各欄・OK ボタンの有効/無効を更新する。"""
        is_kohya = self.kohya_check.isChecked()
        self.config_label.setEnabled(is_kohya)
        # 追加ボタンは常に押せる (追加すると Kohya 取り込みに切り替わる)。オフの間は一覧を無効表示にし、
        # 選択結果にも含めない
        self.config_list.setEnabled(is_kohya)
        self.dataset_name_edit.setEnabled(is_kohya)
        self.version_name_edit.setEnabled(is_kohya)
        self.parent_version_combo.setEnabled(is_kohya)
        # 共通タグは普段の画像のタグ (Tag) に付く。Kohya 取り込みとは独立 (Issue #1409)
        self.folder_tags_label.setVisible(not is_kohya)
        self.folder_table.setEnabled(not is_kohya)
        if not is_kohya and self._scanning_subfolders:
            self.folder_empty_label.setText(_SCANNING_STATUS_TEXT)
            self.folder_table.setVisible(False)
            self.folder_empty_label.setVisible(True)
        else:
            self.folder_empty_label.setText(
                self._subfolder_error_text or "画像を含むサブフォルダはありません"
            )
            self.folder_table.setVisible(not is_kohya and self.folder_table.rowCount() > 0)
            self.folder_empty_label.setVisible(not is_kohya and self.folder_table.rowCount() == 0)
        self.kohya_label.setVisible(is_kohya)
        self.kohya_table.setVisible(is_kohya and self.kohya_table.rowCount() > 0)
        self.kohya_summary_label.setVisible(is_kohya)
        self.remove_config_button.setEnabled(is_kohya and len(self.config_list.selectedItems()) > 0)
        has_directory = bool(self.directory_edit.text().strip())
        # Kohya 取り込みではデータセット名が必須
        name_ok = not is_kohya or bool(self.dataset_name_edit.text().strip())
        # Kohya 取り込みではスキャン完了かつ取り込むフォルダが 1 つ以上必要 (スキャン中・0 フォルダ時は不可)
        folders_ok = True
        if is_kohya and self._scanning_kohya:
            folders_ok = False
            self.kohya_summary_label.setText(_SCANNING_STATUS_TEXT)
        elif is_kohya and self._kohya_table_is_current():
            overrides = self._collect_folder_overrides()
            included = [override for override in overrides if override.include]
            folders_ok = len(included) > 0
            self.kohya_summary_label.setText(self._kohya_summary_text(len(overrides), len(included)))
        elif is_kohya:
            folders_ok = False
            self.kohya_summary_label.setText("ディレクトリを確定するとフォルダを一覧します")
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(has_directory and name_ok and folders_ok)

    def _kohya_summary_text(self, folder_count: int, included_count: int) -> str:
        """Kohya フォルダ表の下に出す要約 (取り込むフォルダ数・学習テキストの無い画像数)。"""
        if self._kohya_error_text:
            return self._kohya_error_text
        if folder_count == 0:
            return (
                "取り込める <数字>_<名前> フォルダがありません "
                "(学習プロジェクト全体でなく、画像フォルダの親を選んでください)"
            )
        without_text = 0
        for row in range(self.kohya_table.rowCount()):
            include_item = self.kohya_table.item(row, _K_INCLUDE_COLUMN)
            count_item = self.kohya_table.item(row, _K_NO_TEXT_COLUMN)
            if include_item is not None and include_item.checkState() == Qt.CheckState.Checked:
                without_text += int(count_item.text()) if count_item is not None else 0
        text = f"{included_count} / {folder_count} フォルダを取り込みます"
        if without_text:
            text += f"。学習テキストの無い画像 {without_text} 枚もそのまま取り込みます"
        return text

    # --- 終了 ---

    def accept(self) -> None:
        """OK で閉じるときに実行中のスキャン worker を停止する。"""
        self._stop_scan_workers()
        super().accept()

    def reject(self) -> None:
        """キャンセルで閉じるときに実行中のスキャン worker を停止する。"""
        self._stop_scan_workers()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ閉鎖時に実行中のスキャン worker を停止する。"""
        self._stop_scan_workers()
        super().closeEvent(event)

    # --- 結果 ---

    def selection(self) -> DatasetSelection | None:
        """現在の入力から選択結果を作る。

        Returns:
            選択結果。ディレクトリ未入力なら None。
        """
        directory_text = self.directory_edit.text().strip()
        if not directory_text:
            return None
        directory = Path(directory_text)
        is_kohya = self.kohya_check.isChecked()
        if is_kohya:
            config_files = tuple(
                Path(self.config_list.item(i).text()) for i in range(self.config_list.count())
            )
            # 表が別ディレクトリのものなら確定値は渡さない (入力欄だけ書き換えて OK した場合)
            overrides = self._collect_folder_overrides() if self._kohya_table_is_current() else None
            return DatasetSelection(
                directory=directory,
                config_files=config_files,
                dataset_name=self.dataset_name_edit.text().strip(),
                version_name=self.version_name_edit.text().strip(),
                kohya_import=True,
                folder_overrides=overrides,
                parent_version_id=self.selected_parent_version_id(),
            )
        # 表が別ディレクトリのものなら共通タグは渡さない (入力欄だけ書き換えて OK した場合)
        folder_tags = self._collect_folder_tags() if directory == self._scanned_directory else {}
        return DatasetSelection(directory=directory, folder_tags=folder_tags)

    @classmethod
    def get_selection(
        cls,
        parent: QWidget | None = None,
        parent_versions_by_dataset: ParentVersionsByDataset | Sequence[ParentVersionEntry] | None = None,
        *,
        parent_versions_provider: ParentVersionsProvider | None = None,
    ) -> DatasetSelection | None:
        """ダイアログを表示し、OK なら選択結果を返す。

        Args:
            parent: 親ウィジェット。
            parent_versions_by_dataset: データセットごとの親の版候補。
            parent_versions_provider: データセット名から親の版候補を返す関数。

        Returns:
            選択結果。キャンセル時は None。
        """
        dialog = cls(
            parent,
            parent_versions_by_dataset=parent_versions_by_dataset,
            parent_versions_provider=parent_versions_provider,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selection()
        return None
