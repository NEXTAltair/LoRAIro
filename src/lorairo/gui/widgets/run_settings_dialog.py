"""実行詳細設定モーダル (Wireframes v12 Frame 3 RunSettings)。

パイプライン実行前の runtime オプションを 1 つのモーダルで提示する
(DS AnnotateScreen RunSettings)。並列実行数 / リトライ / 失敗時の挙動 /
rating ゲート / 既存値上書き / dedupe / dry-run の 7 項目を DS の行レイアウトで
並べる。

バックエンド配線状況 (Issue #789):
- ``rating_gate`` / ``dry_run``: 実装済の概念 (moderation preflight / dry-run)。
  操作可能で :class:`RunOptions` に反映する。
- ``concurrency`` / ``retries`` / ``on_fail`` / ``overwrite``: worker 側未実装の
  ため disabled 表示 (見せかけ操作を作らない)。実 run への適用は後続 backend
  issue で controller→worker_service→AnnotationWorker に配線する。
- ``dedupe``: multimodal は常時 dedupe (ledger と整合) のため ON 固定 disabled。

SegmentedControl は DS 部品ライブラリの DsSegmentedControl (Part of #852) を使う。
``SegmentedControl`` は後方互換エイリアスとして維持する。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from .ds.ds_segmented_control import DsSegmentedControl

# 後方互換エイリアス: 既存テスト・呼び出し元が SegmentedControl として参照できるよう維持する
SegmentedControl = DsSegmentedControl

_UNIMPLEMENTED_TOOLTIP = "バックエンド未実装 — 後続 issue で worker に配線予定"
_DEDUPE_TOOLTIP = "multimodal は常時 dedupe (同一推論を 1 回に集約)。常に ON。"
_DISPATCH_MODE_TOOLTIP = (
    "Batch API は batch-capable な選択モデルのみ async 送信できる。"
    "非対応モデルが混在する場合は dispatch を拒否する (ADR 0076)。"
)


@dataclass(frozen=True)
class RunOptions:
    """パイプライン実行 runtime オプション (DS RunSettings の確定値)。

    Attributes:
        concurrency: 並列推論ワーカー数。
        retries: 失敗時の自動リトライ上限。
        on_fail: リトライ上限後の挙動 ("skip" / "stop")。
        rating_gate: 送信前 moderation preflight を行うか。
        overwrite: 既存アノテーションを上書きするか。
        dedupe: multimodal 推論を 1 回に集約するか (常時 True)。
        dry_run: 実推論せずジョブ件数・推定のみ検証するか。
        dispatch_mode: 送信方式 ("sync" = 同期実行 / "batch_api" = async Provider Batch API)。
    """

    concurrency: int = 4
    retries: int = 2
    on_fail: str = "skip"
    rating_gate: bool = True
    overwrite: bool = False
    dedupe: bool = True
    dry_run: bool = False
    dispatch_mode: str = "sync"


class RunSettingsDialog(QDialog):
    """実行詳細設定モーダル (DS Frame 3 RunSettings)。

    :meth:`run_options` で確定値を :class:`RunOptions` として返す。
    rating_gate / dry_run のみ操作可能、未実装オプションは disabled。
    """

    def __init__(self, staged_count: int, parent: QWidget | None = None) -> None:
        """モーダルを構築する。

        Args:
            staged_count: 対象ステージング枚数 (ヘッダ表示用)。
            parent: 親 widget。
        """
        super().__init__(parent)
        self.setWindowTitle("実行の詳細設定")
        self.setObjectName("runSettingsDialog")
        self.setModal(True)

        layout = QVBoxLayout(self)

        header = QLabel(f"このパイプライン実行に適用 · staged {staged_count} 枚", self)
        header.setObjectName("runSettingsHeader")
        header.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        layout.addWidget(header)

        # 並列実行数 (未実装 → disabled)
        self._concurrency = self._add_segment_row(
            layout,
            "並列実行数 concurrency",
            "同時に走らせる推論ワーカー数。多いほど速いが GPU/レート上限に注意。",
            [("1", "1"), ("2", "2"), ("4", "4"), ("8", "8")],
            "4",
            enabled=False,
        )
        # リトライ回数 (未実装 → disabled)
        self._retries = self._add_segment_row(
            layout,
            "リトライ回数 retries",
            "失敗した推論を自動再試行する上限回数 (指数バックオフ)。",
            [("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")],
            "2",
            enabled=False,
        )
        # 失敗時の挙動 (未実装 → disabled)
        self._on_fail = self._add_segment_row(
            layout,
            "失敗時の挙動 on failure",
            "リトライ上限後の扱い。skip=その画像だけ飛ばす / stop=ジョブ全体を停止。",
            [("skip", "スキップ"), ("stop", "停止")],
            "skip",
            enabled=False,
        )
        # rating ゲート (実装済 → 操作可)
        self._rating_gate = self._add_segment_row(
            layout,
            "rating ゲート preflight",
            "X / XXX 判定の画像は annotation API に送らない (推奨)。",
            [("on", "ON"), ("off", "OFF")],
            "on",
            enabled=True,
        )
        # 既存値の上書き (未実装 → disabled)
        self._overwrite = self._add_segment_row(
            layout,
            "既存値の上書き overwrite",
            "既にアノテーション済みの枠はスキップ (off)。",
            [("off", "OFF"), ("on", "ON")],
            "off",
            enabled=False,
        )
        # dedupe (常時 ON → disabled)
        self._dedupe = self._add_segment_row(
            layout,
            "マルチモーダル dedupe",
            "同一モデルが複数ステージに跨る場合、推論を 1 回にまとめてコストを抑える。",
            [("on", "ON"), ("off", "OFF")],
            "on",
            enabled=False,
            tooltip=_DEDUPE_TOOLTIP,
        )

        # 送信方式 dispatch mode (Batch API 配線済み, #884 Phase 2c)
        self._dispatch_mode = self._add_segment_row(
            layout,
            "送信方式 dispatch mode",
            "同期 = その場で推論。Batch API = Provider の非同期バッチへ送信 (大量・低コスト)。",
            [("sync", "同期"), ("batch_api", "Batch API")],
            "sync",
            enabled=True,
            tooltip=_DISPATCH_MODE_TOOLTIP,
        )

        # dry-run (実装済 → 操作可)
        self._dry_run = QCheckBox("ドライラン dry-run", self)
        self._dry_run.setObjectName("runSettingsDryRun")
        self._dry_run.setToolTip("実際に推論せずジョブ件数・推定コストだけを検証する。")
        layout.addWidget(self._dry_run)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("保存して実行")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _add_segment_row(
        self,
        layout: QVBoxLayout,
        title: str,
        sub: str,
        options: list[tuple[str, str]],
        value: str,
        *,
        enabled: bool,
        tooltip: str | None = None,
    ) -> DsSegmentedControl:
        """1 行 (タイトル + 補足 + DsSegmentedControl) を追加し control を返す。"""
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 6, 0, 6)

        text_box = QVBoxLayout()
        title_label = QLabel(title, row)
        title_label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
        )
        sub_label = QLabel(sub, row)
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_META}px;")
        text_box.addWidget(title_label)
        text_box.addWidget(sub_label)
        row_layout.addLayout(text_box, 1)

        control = DsSegmentedControl(options, value, parent=row)
        if not enabled:
            control.setEnabled(False)
            control.setToolTip(tooltip or _UNIMPLEMENTED_TOOLTIP)
        elif tooltip:
            control.setToolTip(tooltip)
        row_layout.addWidget(control)

        layout.addWidget(row)
        return control

    def run_options(self) -> RunOptions:
        """ダイアログの現在値を :class:`RunOptions` として返す。"""
        return RunOptions(
            concurrency=int(self._concurrency.value()),
            retries=int(self._retries.value()),
            on_fail=self._on_fail.value(),
            rating_gate=self._rating_gate.value() == "on",
            overwrite=self._overwrite.value() == "on",
            dedupe=self._dedupe.value() == "on",
            dry_run=self._dry_run.isChecked(),
            dispatch_mode=self._dispatch_mode.value(),
        )
