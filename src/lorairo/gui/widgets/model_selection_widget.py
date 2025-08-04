# src/lorairo/gui/widgets/model_selection_widget.py

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...services.annotator_lib_adapter import AnnotatorLibAdapter
from ...utils.log import logger


@dataclass
class ModelInfo:
    """モデル情報データクラス"""

    name: str
    provider: str
    capabilities: list[str]  # ["caption", "tags", "scores"] - 実際の機能（ModelTypeと一致）
    api_model_id: str | None
    requires_api_key: bool
    estimated_size_gb: float | None
    is_recommended: bool = False


class ModelSelectionWidget(QWidget):
    """
    動的モデル選択ウィジェット

    機能:
    - DBからの動的モデル取得
    - プロバイダー・機能タイプによるフィルタリング
    - チェックボックス式複数選択
    - 推奨モデル自動選択
    """

    # シグナル
    model_selection_changed = Signal(list)  # selected_model_names
    selection_count_changed = Signal(int, int)  # selected_count, total_count

    def __init__(
        self,
        parent: QWidget | None = None,
        annotator_adapter: AnnotatorLibAdapter | None = None,
        mode: str = "simple",  # "simple" or "advanced"
    ) -> None:
        super().__init__(parent)

        self.annotator_adapter = annotator_adapter
        self.mode = mode  # 簡単モード or 詳細モード

        # モデル情報
        self.all_models: list[ModelInfo] = []
        self.filtered_models: list[ModelInfo] = []
        self.model_checkboxes: dict[str, QCheckBox] = {}

        # フィルタ状態
        self.current_provider_filter: str | None = None
        self.current_capability_filters: list[str] = []

        # UI設定
        self.setup_ui()

        # モデル情報の初期ロード
        if self.annotator_adapter:
            self.load_models()

        logger.debug(f"ModelSelectionWidget initialized in {mode} mode")

    def setup_ui(self) -> None:
        """UI初期化"""
        self.setObjectName("modelSelectionWidget")

        # メインレイアウト
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # 制御ボタン領域
        self.setup_control_buttons(main_layout)

        # モデル表示領域
        self.setup_model_display_area(main_layout)

        # 選択状況表示
        self.setup_status_display(main_layout)

    def setup_control_buttons(self, parent_layout: QVBoxLayout) -> None:
        """制御ボタン領域設定"""
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(6)

        # 全選択ボタン
        self.btn_select_all = QPushButton("全選択")
        self.btn_select_all.setMaximumSize(55, 24)
        self.btn_select_all.clicked.connect(self.select_all_models)
        self.btn_select_all.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 3px 6px;
                border: 1px solid #4CAF50;
                border-radius: 3px;
                background-color: #f0f8f0;
                color: #2E7D32;
            }
            QPushButton:hover { background-color: #e8f5e8; }
            QPushButton:pressed { background-color: #4CAF50; color: white; }
        """)

        # 全解除ボタン
        self.btn_deselect_all = QPushButton("全解除")
        self.btn_deselect_all.setMaximumSize(55, 24)
        self.btn_deselect_all.clicked.connect(self.deselect_all_models)
        self.btn_deselect_all.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 3px 6px;
                border: 1px solid #f44336;
                border-radius: 3px;
                background-color: #fff8f8;
                color: #c62828;
            }
            QPushButton:hover { background-color: #ffebee; }
            QPushButton:pressed { background-color: #f44336; color: white; }
        """)

        # 推奨選択ボタン
        self.btn_select_recommended = QPushButton("推奨選択")
        self.btn_select_recommended.setMaximumSize(65, 24)
        self.btn_select_recommended.clicked.connect(self.select_recommended_models)
        self.btn_select_recommended.setToolTip("推奨モデルを自動選択")
        self.btn_select_recommended.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 3px 6px;
                border: 1px solid #2196F3;
                border-radius: 3px;
                background-color: #f0f8ff;
                color: #1976D2;
            }
            QPushButton:hover { background-color: #e3f2fd; }
            QPushButton:pressed { background-color: #2196F3; color: white; }
        """)

        control_layout.addWidget(self.btn_select_all)
        control_layout.addWidget(self.btn_deselect_all)
        control_layout.addWidget(self.btn_select_recommended)
        control_layout.addStretch()

        parent_layout.addWidget(control_frame)

    def setup_model_display_area(self, parent_layout: QVBoxLayout) -> None:
        """モデル表示領域設定"""
        # スクロールエリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setMinimumHeight(120 if self.mode == "advanced" else 80)
        self.scroll_area.setMaximumHeight(200 if self.mode == "advanced" else 120)

        # スクロールエリア内容
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(6, 6, 6, 6)
        self.scroll_layout.setSpacing(2)

        # プレースホルダーラベル
        self.placeholder_label = QLabel()
        if self.mode == "simple":
            self.placeholder_label.setText(
                "📋 推奨AIモデル (DB自動選択)\n\n"
                "下記の推奨構成から複数選択できます:\n"
                "🎯 高品質Caption生成\n"
                "🏷️ 高精度タグ生成\n"
                "⭐ 品質評価\n\n"
                "モデル一覧は設定されたAPIキーと\n"
                "利用可能なローカルモデルに基づいて\n"
                "自動表示されます"
            )
            self.placeholder_label.setStyleSheet("""
                color: #666;
                font-style: italic;
                padding: 12px;
                font-size: 10px;
                line-height: 1.3;
                background-color: #f0f8ff;
                border: 1px dashed #2196F3;
                border-radius: 4px;
            """)
        else:
            self.placeholder_label.setText(
                "プロバイダーと機能タイプを選択すると、対象モデルがここに表示されます\n\n"
                "🔍 フィルタリング手順:\n"
                "1. プロバイダーを選択 (OpenAI/Anthropic/Google/Local等)\n"
                "2. 機能タイプを選択 (Caption/Tagger/Scorer)\n"
                "3. 対象モデルが自動表示されます\n"
                "4. チェックボックスで複数選択可能\n\n"
                "📊 利用可能なモデル数はプロバイダーと機能によって変動します"
            )
            self.placeholder_label.setStyleSheet("""
                color: #666;
                font-style: italic;
                padding: 15px;
                font-size: 10px;
                line-height: 1.4;
                background-color: #f9f9f9;
                border: 1px dashed #ccc;
                border-radius: 4px;
            """)

        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.placeholder_label.setWordWrap(True)
        self.scroll_layout.addWidget(self.placeholder_label)

        self.scroll_area.setWidget(self.scroll_content)
        parent_layout.addWidget(self.scroll_area)

    def setup_status_display(self, parent_layout: QVBoxLayout) -> None:
        """選択状況表示設定"""
        self.status_label = QLabel()
        if self.mode == "simple":
            self.status_label.setText("選択数: 0 (推奨)")
            self.status_label.setToolTip("推奨モデルから選択されている数")
        else:
            self.status_label.setText("選択数: 0 (フィルタ後)")
            self.status_label.setToolTip(
                "現在のフィルタリング条件で表示されたモデルのうち、選択されている数"
            )

        self.status_label.setStyleSheet("color: #333; font-size: 11px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        parent_layout.addWidget(self.status_label)

    def load_models(self) -> None:
        """モデル情報をAnnotatorLibAdapterから取得"""
        try:
            if not self.annotator_adapter:
                logger.warning("AnnotatorLibAdapter not available")
                return

            # モデル情報取得
            models_metadata = self.annotator_adapter.get_available_models_with_metadata()

            # ModelInfoに変換
            self.all_models = []
            for model_data in models_metadata:
                model_info = ModelInfo(
                    name=model_data.get("name", ""),
                    provider=model_data.get("provider", "unknown"),
                    capabilities=self._infer_capabilities(model_data),
                    api_model_id=model_data.get("api_model_id"),
                    requires_api_key=model_data.get("requires_api_key", False),
                    estimated_size_gb=model_data.get("estimated_size_gb"),
                    is_recommended=self._is_recommended_model(model_data.get("name", "")),
                )
                self.all_models.append(model_info)

            logger.info(f"Loaded {len(self.all_models)} models from AnnotatorLibAdapter")

            # 初期表示更新
            self.update_model_display()

        except Exception as e:
            logger.error(f"Failed to load models: {e}")

    def _infer_capabilities(self, model_data: dict[str, Any]) -> list[str]:
        """モデルタイプから機能をマッピング"""
        model_type = model_data.get("model_type", "")

        # DBのmodel_typeカラムから機能をマッピング
        type_mapping = {
            "multimodal": ["caption", "tag"],
            "caption": ["caption"],
            "tag": ["tag"],
            "score": ["score"],
        }

        return type_mapping.get(model_type, ["caption"])

    def _is_recommended_model(self, model_name: str) -> bool:
        """推奨モデルかどうか判定"""
        name_lower = model_name.lower()

        # 高品質Caption生成モデル
        caption_recommended = ["gpt-4o", "claude-3-5-sonnet", "claude-3-sonnet", "gemini-pro"]

        # 高精度タグ生成モデル
        tags_recommended = ["wd-v1-4", "wd-tagger", "deepdanbooru", "wd-swinv2"]

        # 品質評価モデル
        scores_recommended = ["clip-aesthetic", "musiq", "aesthetic-scorer"]

        all_recommended = caption_recommended + tags_recommended + scores_recommended

        return any(rec in name_lower for rec in all_recommended)

    def apply_filters(self, provider: str | None = None, capabilities: list[str] | None = None) -> None:
        """フィルタリング適用"""
        self.current_provider_filter = provider
        self.current_capability_filters = capabilities or []
        self.update_model_display()

    def update_model_display(self) -> None:
        """モデル表示更新"""
        # 現在のチェックボックスをクリア
        self.clear_model_display()

        # フィルタリング実行
        if self.mode == "simple":
            self.filtered_models = [m for m in self.all_models if m.is_recommended]
        else:
            self.filtered_models = self._apply_advanced_filters()

        # フィルタされたモデルがない場合
        if not self.filtered_models:
            self.placeholder_label.setVisible(True)
            self.update_selection_count()
            return

        # プレースホルダーを非表示
        self.placeholder_label.setVisible(False)

        # プロバイダー別にグループ化して表示
        provider_groups = self._group_models_by_provider()

        for provider, models in provider_groups.items():
            if models:
                self._add_provider_group(provider, models)

        self.update_selection_count()

    def _apply_advanced_filters(self) -> list[ModelInfo]:
        """詳細モード用フィルタリング"""
        filtered = self.all_models

        # プロバイダーフィルタ
        if self.current_provider_filter and self.current_provider_filter != "すべて":
            filtered = [m for m in filtered if m.provider.lower() == self.current_provider_filter.lower()]

        # 機能フィルタ
        if self.current_capability_filters:
            filtered = [
                m for m in filtered if any(cap in m.capabilities for cap in self.current_capability_filters)
            ]

        return filtered

    def _group_models_by_provider(self) -> dict[str, list[ModelInfo]]:
        """プロバイダー別にモデルをグループ化"""
        groups: dict[str, list[ModelInfo]] = {}
        for model in self.filtered_models:
            provider = model.provider or "local"
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(model)
        return groups

    def _add_provider_group(self, provider: str, models: list[ModelInfo]) -> None:
        """プロバイダーグループをUIに追加"""
        # プロバイダーラベル
        provider_icons = {"openai": "🤖", "anthropic": "🧠", "google": "🌟", "local": "💻"}
        icon = provider_icons.get(provider.lower(), "🔧")

        provider_label = QLabel(f"{icon} {provider.title()} Models")
        provider_label.setStyleSheet("""
            font-size: 9px;
            font-weight: bold;
            color: #666;
            padding: 2px 0px;
        """)
        self.scroll_layout.addWidget(provider_label)

        # モデルチェックボックス
        for model in models:
            checkbox = self._create_model_checkbox(model)
            self.model_checkboxes[model.name] = checkbox
            self.scroll_layout.addWidget(checkbox)

    def _create_model_checkbox(self, model: ModelInfo) -> QCheckBox:
        """モデル用チェックボックス作成"""
        # 表示名作成
        display_name = model.name
        if model.requires_api_key:
            display_name += " (API)"
        if model.estimated_size_gb:
            display_name += f" ({model.estimated_size_gb:.1f}GB)"

        checkbox = QCheckBox(display_name)
        checkbox.setObjectName(f"checkBox_{model.name}")
        checkbox.setToolTip(self._create_model_tooltip(model))
        checkbox.stateChanged.connect(self.on_model_selection_changed)

        # スタイル
        checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 10px;
                font-weight: normal;
                margin: 1px 0px;
                padding: 2px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #ccc;
                background-color: white;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #4CAF50;
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)

        return checkbox

    def _create_model_tooltip(self, model: ModelInfo) -> str:
        """モデル用ツールチップ作成"""
        tooltip_parts = [f"プロバイダー: {model.provider}", f"機能: {', '.join(model.capabilities)}"]

        if model.api_model_id:
            tooltip_parts.append(f"API ID: {model.api_model_id}")

        if model.estimated_size_gb:
            tooltip_parts.append(f"サイズ: {model.estimated_size_gb:.1f}GB")

        tooltip_parts.append(f"APIキー必要: {'Yes' if model.requires_api_key else 'No'}")

        return "\n".join(tooltip_parts)

    def clear_model_display(self) -> None:
        """モデル表示をクリア"""
        # 既存のチェックボックスを削除
        for checkbox in self.model_checkboxes.values():
            checkbox.setParent(None)
            checkbox.deleteLater()

        self.model_checkboxes.clear()

        # レイアウトから削除（プレースホルダー以外）
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget() != self.placeholder_label:
                widget = item.widget()
                self.scroll_layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

    @Slot()
    def on_model_selection_changed(self) -> None:
        """モデル選択変更時の処理"""
        selected_models = self.get_selected_models()
        self.update_selection_count()
        self.model_selection_changed.emit(selected_models)

    def get_selected_models(self) -> list[str]:
        """選択されたモデル名のリストを取得"""
        selected: list[str] = []
        for model_name, checkbox in self.model_checkboxes.items():
            if checkbox.isChecked():
                selected.append(model_name)
        return selected

    def update_selection_count(self) -> None:
        """選択数表示を更新"""
        selected_count = len(self.get_selected_models())
        total_count = len(self.filtered_models)

        if self.mode == "simple":
            self.status_label.setText(f"選択数: {selected_count} (推奨)")
        else:
            self.status_label.setText(f"選択数: {selected_count} (フィルタ後)")

        self.selection_count_changed.emit(selected_count, total_count)

    @Slot()
    def select_all_models(self) -> None:
        """全モデル選択"""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(True)

    @Slot()
    def deselect_all_models(self) -> None:
        """全モデル選択解除"""
        for checkbox in self.model_checkboxes.values():
            checkbox.setChecked(False)

    @Slot()
    def select_recommended_models(self) -> None:
        """推奨モデル選択"""
        for model_name, checkbox in self.model_checkboxes.items():
            # 対応するModelInfoを検索
            model_info = next((m for m in self.filtered_models if m.name == model_name), None)
            if model_info and model_info.is_recommended:
                checkbox.setChecked(True)

    def set_selected_models(self, model_names: list[str]) -> None:
        """指定されたモデルを選択状態に設定"""
        for model_name, checkbox in self.model_checkboxes.items():
            checkbox.setChecked(model_name in model_names)


if __name__ == "__main__":
    # Tier2: UI想定動作のみ確認（ダミーチェックボックスを __main__ 内でのみ挿入）
    import sys

    from PySide6.QtWidgets import QApplication, QCheckBox, QMainWindow

    from ...utils.log import initialize_logging

    # ログはコンソール優先
    initialize_logging({"level": "DEBUG", "file": None})
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("ModelSelectionWidget テスト (Tier2)")
    widget = ModelSelectionWidget(mode="simple")  # 最小構成
    window.setCentralWidget(widget)
    window.resize(600, 400)

    # selection_count_changed をprintで確認
    def _on_selection_count_changed(selected: int, total: int) -> None:
        print(f"[Signal] selection_count_changed: {selected}/{total}")

    widget.selection_count_changed.connect(_on_selection_count_changed)

    # __main__ 内限定の補助: ダミーモデルをUIに挿入してシグナル動作確認
    def _inject_dummy_models_for_demo(_w: ModelSelectionWidget) -> None:
        # ダミーModelInfo相当のリストを __main__ 限定で埋める
        _w.all_models = [
            ModelInfo(
                name="gpt-4o",
                provider="openai",
                capabilities=["caption"],
                api_model_id="gpt-4o",
                requires_api_key=True,
                estimated_size_gb=None,
                is_recommended=True,
            ),
            ModelInfo(
                name="wd-v1-4",
                provider="local",
                capabilities=["tag"],
                api_model_id=None,
                requires_api_key=False,
                estimated_size_gb=2.0,
                is_recommended=True,
            ),
            ModelInfo(
                name="clip-aesthetic",
                provider="local",
                capabilities=["score"],
                api_model_id=None,
                requires_api_key=False,
                estimated_size_gb=0.5,
                is_recommended=True,
            ),
        ]
        # 表示更新で filtered_models と model_checkboxes を構築
        _w.update_model_display()

        # もしプレースホルダーのみ表示だった場合は手動でチェックボックスを挿入
        if not _w.model_checkboxes:
            # プレースホルダーを非表示にして手動追加
            _w.placeholder_label.setVisible(False)
            for m in _w.all_models:
                cb = QCheckBox(m.name)
                cb.stateChanged.connect(_w.on_model_selection_changed)
                _w.model_checkboxes[m.name] = cb
                _w.filtered_models.append(m)
                _w.scroll_layout.addWidget(cb)
            _w.update_selection_count()

    _inject_dummy_models_for_demo(widget)

    # 想定動作: 全選択 → 全解除 → 推奨選択 を順に呼ぶ
    widget.select_all_models()
    widget.deselect_all_models()
    widget.select_recommended_models()

    window.show()
    sys.exit(app.exec())
