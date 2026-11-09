"""生成メタデータ詳細表示ウィジェットと遅延展開 JSON ツリーモデル (Issue #1483)。

SelectedImageDetailsWidget 内で画像の生成メタデータ解析状態 (5 状態)、
抽出済みフィールド、および原データ (raw_workflow / raw_prompt / raw_parameters 等) の
遅延展開ツリーを表示する。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .. import theme

STATUS_DISPLAY_LABELS: dict[str, str] = {
    "none": "生成メタデータなし",
    "no_metadata": "生成メタデータなし",
    "parsed": "解析済み",
    "partial": "部分解析",
    "unsupported": "未対応形式",
    "failed": "解析失敗",
}

TOOL_DISPLAY_LABELS: dict[str, str] = {
    "sd_webui": "A1111 / SD WebUI (sd_webui)",
    "a1111": "A1111 / SD WebUI (a1111)",
    "comfyui": "ComfyUI (comfyui)",
    "unknown": "不明 (unknown)",
}


class _JsonTreeNode:
    """LazyJsonTreeModel の内部ノード。子ノードは fetchMore 呼び出しまで生成しない。"""

    __slots__ = ("children", "fetched", "key", "parent", "unparsed_json", "value")

    def __init__(
        self,
        key: str,
        value: Any,
        parent: _JsonTreeNode | None = None,
        *,
        unparsed_json: str | None = None,
    ) -> None:
        self.key = key
        self.value = value
        self.parent = parent
        self.unparsed_json = unparsed_json
        self.children: list[_JsonTreeNode] = []
        self.fetched: bool = False

    def row(self) -> int:
        if self.parent is None:
            return 0
        return self.parent.children.index(self)

    @property
    def is_expandable(self) -> bool:
        if self.unparsed_json is not None:
            return bool(self.unparsed_json.strip())
        if isinstance(self.value, Mapping):
            return len(self.value) > 0
        if isinstance(self.value, list | tuple):
            return len(self.value) > 0
        return False

    def summary_text(self) -> str:
        if self.unparsed_json is not None:
            stripped = self.unparsed_json.strip()
            if stripped.startswith("{"):
                return "{...} (JSON)"
            if stripped.startswith("["):
                return "[...] (JSON)"
            preview = stripped.replace("\n", " ")
            return preview[:80] + ("…" if len(preview) > 80 else "")
        if isinstance(self.value, Mapping):
            return f"{{...}} ({len(self.value)} keys)"
        if isinstance(self.value, list | tuple):
            return f"[...] ({len(self.value)} items)"
        if self.value is None:
            return "null"
        text = str(self.value).replace("\n", " ")
        return text[:120] + ("…" if len(text) > 120 else "")


def _build_child_node(key: str, raw_val: Any, parent: _JsonTreeNode) -> _JsonTreeNode:
    """値を検査し、遅延 JSON 文字列または構造化データとして子ノードを 1 つ作成する。"""
    if isinstance(raw_val, str):
        stripped = raw_val.strip()
        if (
            (stripped.startswith("{") and stripped.endswith("}"))
            or (stripped.startswith("[") and stripped.endswith("]"))
            or "\n" in stripped
        ):
            return _JsonTreeNode(key, None, parent, unparsed_json=raw_val)
    return _JsonTreeNode(key, raw_val, parent)


class LazyJsonTreeModel(QAbstractItemModel):
    """canFetchMore / fetchMore により展開時にのみ子ノードを構築する JSON / 原データツリーモデル。

    巨大な ComfyUI workflow / prompt JSON でも選択時にはトップレベル項目のみ保持し、
    ノード展開時に直下の子ノードだけを生成するため GUI スレッドをブロックしない。
    """

    def __init__(self, data: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root = _JsonTreeNode("root", None)
        self._root.fetched = True
        if data is not None:
            self.set_json_data(data)

    def clear(self) -> None:
        """ツリーモデルを空にする。"""
        self.beginResetModel()
        self._root = _JsonTreeNode("root", None)
        self._root.fetched = True
        self.endResetModel()

    def set_json_data(self, data: Any) -> None:
        """ルートデータを設定し、トップレベルノードのみ構築する (孫以降は未構築)。"""
        self.beginResetModel()
        self._root = _JsonTreeNode("root", None)
        self._root.fetched = True

        parsed_top = data
        if isinstance(data, str):
            stripped = data.strip()
            if stripped:
                try:
                    parsed_top = json.loads(stripped)
                except (json.JSONDecodeError, TypeError, ValueError):
                    parsed_top = data
            else:
                parsed_top = None

        if isinstance(parsed_top, Mapping):
            for k, v in parsed_top.items():
                if v is None or v == "":
                    continue
                self._root.children.append(_build_child_node(str(k), v, self._root))
        elif isinstance(parsed_top, list | tuple):
            for idx, item in enumerate(parsed_top):
                self._root.children.append(_build_child_node(f"[{idx}]", item, self._root))
        elif parsed_top is not None and str(parsed_top).strip():
            self._root.children.append(_JsonTreeNode("value", parsed_top, self._root))

        self.endResetModel()

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        del parent
        return 2

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "キー" if section == 0 else "値"
        return None

    def _node_from_index(self, index: QModelIndex | QPersistentModelIndex) -> _JsonTreeNode:
        if index.isValid():
            internal = index.internalPointer()
            if isinstance(internal, _JsonTreeNode):
                return internal
        return self._root

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        if 0 <= row < len(parent_node.children):
            return self.createIndex(row, column, parent_node.children[row])
        return QModelIndex()

    def parent(  # type: ignore[override]
        self, index: QModelIndex | QPersistentModelIndex
    ) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        node = self._node_from_index(index)
        parent_node = node.parent
        if parent_node is None or parent_node is self._root:
            return QModelIndex()
        return self.createIndex(parent_node.row(), 0, parent_node)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        node = self._node_from_index(parent)
        return len(node.children)

    def hasChildren(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            return len(self._root.children) > 0
        node = self._node_from_index(parent)
        if node.fetched:
            return len(node.children) > 0
        return node.is_expandable

    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex) -> bool:
        if not parent.isValid():
            return False
        node = self._node_from_index(parent)
        return not node.fetched and node.is_expandable

    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex) -> None:
        if not parent.isValid():
            return
        node = self._node_from_index(parent)
        if node.fetched:
            return

        new_children = self._materialize_direct_children(node)
        node.fetched = True
        if not new_children:
            return

        self.beginInsertRows(parent, 0, len(new_children) - 1)
        node.children.extend(new_children)
        self.endInsertRows()

    @staticmethod
    def _materialize_direct_children(node: _JsonTreeNode) -> list[_JsonTreeNode]:
        """対象ノードの直下の子ノードのみを生成する (孫以降は生成しない)。"""
        target_value = node.value
        if node.unparsed_json is not None:
            raw_text = node.unparsed_json
            node.unparsed_json = None
            try:
                target_value = json.loads(raw_text)
                node.value = target_value
            except (json.JSONDecodeError, TypeError, ValueError):
                # JSON として解釈できない場合は行単位または全文の葉ノードにする
                lines = [line for line in raw_text.splitlines() if line.strip()]
                if len(lines) > 1:
                    return [_JsonTreeNode(f"[{i}]", line, node) for i, line in enumerate(lines)]
                return [_JsonTreeNode("text", raw_text, node)]

        children: list[_JsonTreeNode] = []
        if isinstance(target_value, Mapping):
            for k, v in target_value.items():
                children.append(_build_child_node(str(k), v, node))
        elif isinstance(target_value, list | tuple):
            for idx, item in enumerate(target_value):
                children.append(_build_child_node(f"[{idx}]", item, node))
        return children

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        node = self._node_from_index(index)
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return node.key
            return node.summary_text()
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 0:
                return node.key
            if isinstance(node.value, str | int | float | bool):
                return str(node.value)
            return node.summary_text()
        return None

    def is_node_fetched(self, index: QModelIndex) -> bool:
        """指定インデックスの子ノードが展開・構築済みかを返す (テスト・診断用)。"""
        if not index.isValid():
            return True
        return self._node_from_index(index).fetched


class GenerationMetadataDisplayWidget(QWidget):
    """選択画像の生成メタデータ詳細表示ウィジェット (Issue #1483)。

    5 つの状態 (`none`/`no_metadata`, `parsed`, `partial`, `unsupported`, `failed`) を
    明確に区別して表示し、抽出済みフィールドと遅延展開 JSON ツリーを提供する。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_status: str = "none"
        self._setup_ui()
        self.clear_display()

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(6)

        self.group_box = QGroupBox("生成メタデータ", self)
        group_layout = QVBoxLayout(self.group_box)
        group_layout.setContentsMargins(8, 8, 8, 8)
        group_layout.setSpacing(6)

        # 状態バッジ / ラベルと失敗理由ラベル
        self.label_status = QLabel(self.group_box)
        self.label_status.setObjectName("labelGenerationStatus")
        self._make_selectable(self.label_status)
        group_layout.addWidget(self.label_status)

        self.label_error_reason = QLabel(self.group_box)
        self.label_error_reason.setObjectName("labelGenerationErrorReason")
        self.label_error_reason.setWordWrap(True)
        self.label_error_reason.setStyleSheet(f"color: {theme.ERR}; font-size: 11px;")
        self._make_selectable(self.label_error_reason)
        self.label_error_reason.setVisible(False)
        group_layout.addWidget(self.label_error_reason)

        # 抽出済みフィールドコンテナ
        self.fields_container = QWidget(self.group_box)
        form = QFormLayout(self.fields_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        self.label_tool = self._create_value_label()
        self.label_model_name = self._create_value_label()
        self.label_loras = self._create_value_label(word_wrap=True)
        self.label_positive_prompt = self._create_value_label(word_wrap=True)
        self.label_negative_prompt = self._create_value_label(word_wrap=True)
        self.label_seed = self._create_value_label()
        self.label_steps = self._create_value_label()
        self.label_sampler = self._create_value_label()
        self.label_scheduler = self._create_value_label()
        self.label_cfg = self._create_value_label()
        self.label_denoise = self._create_value_label()

        form.addRow(QLabel("ツール:"), self.label_tool)
        form.addRow(QLabel("モデル:"), self.label_model_name)
        form.addRow(QLabel("LoRA:"), self.label_loras)
        form.addRow(QLabel("Positive:"), self.label_positive_prompt)
        form.addRow(QLabel("Negative:"), self.label_negative_prompt)
        form.addRow(QLabel("Seed:"), self.label_seed)
        form.addRow(QLabel("Steps:"), self.label_steps)
        form.addRow(QLabel("Sampler:"), self.label_sampler)
        form.addRow(QLabel("Scheduler:"), self.label_scheduler)
        form.addRow(QLabel("CFG:"), self.label_cfg)
        form.addRow(QLabel("Denoise:"), self.label_denoise)

        group_layout.addWidget(self.fields_container)

        # 遅延展開 Raw / JSON ツリービュー
        self.raw_tree_model = LazyJsonTreeModel(parent=self.group_box)
        self.raw_tree_view = QTreeView(self.group_box)
        self.raw_tree_view.setObjectName("treeViewGenerationRaw")
        self.raw_tree_view.setModel(self.raw_tree_model)
        self.raw_tree_view.setMinimumHeight(120)
        self.raw_tree_view.setAlternatingRowColors(True)
        self.raw_tree_view.setVisible(False)
        group_layout.addWidget(self.raw_tree_view)

        outer_layout.addWidget(self.group_box)

    @staticmethod
    def _make_selectable(label: QLabel) -> None:
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

    def _create_value_label(self, *, word_wrap: bool = False) -> QLabel:
        label = QLabel("-", self.fields_container)
        label.setWordWrap(word_wrap)
        self._make_selectable(label)
        return label

    @property
    def current_status(self) -> str:
        """現在の正規化ステータス ('none' | 'parsed' | 'partial' | 'unsupported' | 'failed')。"""
        return self._current_status

    def clear_display(self) -> None:
        """表示を初期状態 ('生成メタデータなし') にリセットする。"""
        self._current_status = "none"
        self.label_status.setText(STATUS_DISPLAY_LABELS["none"])
        self.label_error_reason.clear()
        self.label_error_reason.setVisible(False)

        for lbl in (
            self.label_tool,
            self.label_model_name,
            self.label_loras,
            self.label_positive_prompt,
            self.label_negative_prompt,
            self.label_seed,
            self.label_steps,
            self.label_sampler,
            self.label_scheduler,
            self.label_cfg,
            self.label_denoise,
        ):
            lbl.setText("-")

        self.fields_container.setVisible(False)
        self.raw_tree_model.clear()
        self.raw_tree_view.setVisible(False)

    def set_generation_metadata(
        self,
        metadata: Any,
        sources: Sequence[Any] | None = None,
    ) -> None:
        """生成メタデータ (ORM 行 / Domain Result / dict / None) を表示に反映する。"""
        if metadata is None:
            self.clear_display()
            return

        normalized = self._normalize_metadata(metadata, sources)
        raw_status = str(normalized.get("status") or "none").strip().lower()
        if raw_status in ("none", "no_metadata", ""):
            self._current_status = "none"
        elif raw_status in STATUS_DISPLAY_LABELS:
            self._current_status = raw_status
        else:
            self._current_status = raw_status

        status_label = STATUS_DISPLAY_LABELS.get(raw_status, raw_status)
        self.label_status.setText(status_label)

        error_reason = normalized.get("error_reason") or normalized.get("error_message")
        if self._current_status == "failed" and error_reason:
            self.label_status.setText(f"{status_label}: {error_reason}")
            self.label_error_reason.setText(str(error_reason))
            self.label_error_reason.setVisible(True)
        elif error_reason:
            self.label_error_reason.setText(str(error_reason))
            self.label_error_reason.setVisible(True)
        else:
            self.label_error_reason.clear()
            self.label_error_reason.setVisible(False)

        if self._current_status == "none":
            self.fields_container.setVisible(False)
            self.raw_tree_model.clear()
            self.raw_tree_view.setVisible(False)
            return

        # フィールド表示の更新
        tool_val = normalized.get("tool")
        if tool_val:
            tool_str = str(tool_val)
            self.label_tool.setText(TOOL_DISPLAY_LABELS.get(tool_str.lower(), tool_str))
        else:
            self.label_tool.setText("-")

        self.label_model_name.setText(self._fmt_value(normalized.get("model_name")))
        self.label_loras.setText(self._fmt_loras(normalized.get("loras")))
        self.label_positive_prompt.setText(self._fmt_value(normalized.get("positive_prompt")))
        self.label_negative_prompt.setText(self._fmt_value(normalized.get("negative_prompt")))
        self.label_seed.setText(self._fmt_value(normalized.get("seed")))
        self.label_steps.setText(self._fmt_value(normalized.get("steps")))
        self.label_sampler.setText(self._fmt_value(normalized.get("sampler")))
        self.label_scheduler.setText(self._fmt_value(normalized.get("scheduler")))
        self.label_cfg.setText(self._fmt_value(normalized.get("cfg")))
        self.label_denoise.setText(self._fmt_value(normalized.get("denoise")))

        self.fields_container.setVisible(
            self._current_status in ("parsed", "partial", "unsupported", "failed")
        )

        # Raw / JSON ツリーの遅延構築
        raw_payload = normalized.get("raw_tree")
        if raw_payload:
            self.raw_tree_model.set_json_data(raw_payload)
            self.raw_tree_view.setVisible(self.raw_tree_model.rowCount() > 0)
        else:
            self.raw_tree_model.clear()
            self.raw_tree_view.setVisible(False)

    @staticmethod
    def _fmt_value(value: Any) -> str:
        if value is None or value == "":
            return "-"
        return str(value)

    @staticmethod
    def _fmt_single_lora_item(item: Any) -> str:
        if isinstance(item, Mapping):
            name = item.get("name") or ""
            weight = item.get("weight")
        elif hasattr(item, "name"):
            name = getattr(item, "name", "")
            weight = getattr(item, "weight", None)
        else:
            return str(item) if item else ""
        if name and weight is not None:
            return f"{name}:{weight}"
        return str(name) if name else ""

    @classmethod
    def _fmt_loras(cls, loras: Any) -> str:
        if not loras:
            return "-"
        if isinstance(loras, str):
            stripped = loras.strip()
            if not stripped:
                return "-"
            try:
                loras = json.loads(stripped)
            except (json.JSONDecodeError, TypeError, ValueError):
                return stripped
        if isinstance(loras, Sequence) and not isinstance(loras, str | bytes):
            formatted = [s for s in (cls._fmt_single_lora_item(it) for it in loras) if s]
            return ", ".join(formatted) if formatted else "-"
        return str(loras)

    @staticmethod
    def _extract_attr_dict(metadata: Any) -> dict[str, Any]:
        params = getattr(metadata, "parameters", None)
        steps = getattr(metadata, "steps", None)
        if steps is None:
            steps = getattr(params, "steps", None)
        cfg = getattr(metadata, "cfg", None)
        if cfg is None:
            cfg = getattr(metadata, "cfg_scale", None)
        if cfg is None:
            cfg = getattr(params, "cfg_scale", None)
        return {
            "status": getattr(metadata, "status", None),
            "tool": getattr(metadata, "tool", None),
            "model_name": getattr(metadata, "model_name", None) or getattr(params, "model_name", None),
            "model_hash": getattr(metadata, "model_hash", None) or getattr(params, "model_hash", None),
            "loras": getattr(metadata, "loras", None)
            or getattr(metadata, "loras_json", None)
            or getattr(params, "loras", None),
            "positive_prompt": getattr(metadata, "positive_prompt", None)
            or getattr(params, "positive_prompt", None),
            "negative_prompt": getattr(metadata, "negative_prompt", None)
            or getattr(params, "negative_prompt", None),
            "seed": getattr(metadata, "seed", None) or getattr(params, "seed", None),
            "steps": steps,
            "sampler": getattr(metadata, "sampler", None) or getattr(params, "sampler", None),
            "scheduler": getattr(metadata, "scheduler", None) or getattr(params, "scheduler", None),
            "cfg": cfg,
            "denoise": getattr(metadata, "denoise", None) or getattr(params, "denoise", None),
            "error_reason": getattr(metadata, "error_reason", None)
            or getattr(metadata, "error_message", None),
            "extra_json": getattr(metadata, "extra_json", None),
            "extra": getattr(metadata, "extra", None) or getattr(params, "extra", None),
            "raw_workflow": getattr(metadata, "raw_workflow", None),
            "raw_prompt": getattr(metadata, "raw_prompt", None),
            "raw_parameters": getattr(metadata, "raw_parameters", None),
            "sources": getattr(metadata, "sources", None),
        }

    @staticmethod
    def _pick_first_extra(extra_dict: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in extra_dict and extra_dict[key] is not None:
                return extra_dict[key]
        return None

    @staticmethod
    def _build_raw_tree(
        data: dict[str, Any],
        sources: Sequence[Any] | None,
        extra_dict: dict[str, Any],
    ) -> dict[str, Any]:
        raw_tree: dict[str, Any] = {}
        for raw_key in ("raw_workflow", "raw_prompt", "raw_parameters"):
            val = data.get(raw_key)
            if val is not None and val != "":
                raw_tree[raw_key] = val

        all_sources = list(sources) if sources else list(data.get("sources") or [])
        for src in all_sources:
            if isinstance(src, Mapping):
                s_key = str(src.get("source_key") or src.get("key") or "source")
                s_val = src.get("raw_text")
            else:
                s_key = str(getattr(src, "source_key", None) or "source")
                s_val = getattr(src, "raw_text", None)
            if s_val:
                mapped_key = f"raw_{s_key}" if s_key in ("workflow", "prompt", "parameters") else s_key
                raw_tree.setdefault(mapped_key, s_val)

        if extra_dict and not raw_tree:
            raw_tree["extra"] = extra_dict
        return raw_tree

    @classmethod
    def _normalize_metadata(cls, metadata: Any, sources: Sequence[Any] | None = None) -> dict[str, Any]:
        """ORM GenerationMetadata / GenerationMetadataResult / dict を統一辞書へ変換する。"""
        data = dict(metadata) if isinstance(metadata, Mapping) else cls._extract_attr_dict(metadata)

        status_obj = data.get("status")
        if status_obj is not None and hasattr(status_obj, "value"):
            data["status"] = status_obj.value

        if not data.get("loras") and data.get("loras_json"):
            data["loras"] = data.get("loras_json")

        if data.get("cfg") is None and data.get("cfg_scale") is not None:
            data["cfg"] = data.get("cfg_scale")

        extra_dict = cls._extract_extra_dict(data.get("extra"), data.get("extra_json"))
        if data.get("scheduler") is None:
            data["scheduler"] = cls._pick_first_extra(
                extra_dict, ("scheduler", "Scheduler", "Schedule type", "schedule_type")
            )
        if data.get("denoise") is None:
            data["denoise"] = cls._pick_first_extra(
                extra_dict, ("denoise", "Denoise", "Denoising strength", "denoising_strength")
            )

        data["raw_tree"] = cls._build_raw_tree(data, sources, extra_dict)
        return data

    @staticmethod
    def _extract_extra_dict(extra: Any, extra_json: Any) -> dict[str, Any]:
        if isinstance(extra, Mapping):
            return dict(extra)
        if isinstance(extra_json, str) and extra_json.strip():
            try:
                parsed = json.loads(extra_json)
                if isinstance(parsed, Mapping):
                    return dict(parsed)
            except (json.JSONDecodeError, TypeError, ValueError):
                return {}
        return {}
