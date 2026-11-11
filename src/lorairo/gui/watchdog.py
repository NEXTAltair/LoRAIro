"""メインスレッドのイベントループ停滞を検知する軽量 watchdog (#1221)。

GUI 操作で重い同期処理がメインスレッドをブロックすると、Windows は 5 秒超で
ウィンドウに「応答なし」を付ける。実際にどの操作でイベントループが止まったかを
事後に追えるよう、一定間隔で tick し前回 tick からの経過が閾値を超えていればログを
残す。監視自体はメインスレッドの QTimer で行うため、ブロック中は tick も遅延し、
その遅延量がそのまま停滞時間の指標になる。

1 秒超の停滞は DEBUG、3 秒超 (「応答なし」に近づく水準) は WARNING で記録する
(#1596)。tick 間隔は閾値より十分短くし、タイマーの揺れだけで検知しないようにする。
"""

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Slot

from ..utils.log import logger


class MainThreadWatchdog(QObject):
    """メインスレッドのイベントループ遅延を検知してログを出す watchdog (#1221, #1596)。

    ``interval_ms`` ごとに tick し、前回 tick からの実経過が ``threshold_ms`` を
    超えていれば (= その間メインスレッドがブロックされ tick が遅延した) DEBUG を、
    ``warning_threshold_ms`` を超えていれば WARNING を記録する。worker やアプリ初期化を
    妨げないよう、監視は単一の QTimer のみで行う。
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = 250,
        threshold_ms: int = 1000,
        warning_threshold_ms: int = 3000,
    ) -> None:
        """watchdog を生成する (開始は :meth:`start`)。

        Args:
            parent: 親 QObject。
            interval_ms: tick 間隔 (ms)。
            threshold_ms: 停滞として DEBUG 記録する前回 tick からの経過閾値 (ms)。
            warning_threshold_ms: 停滞として WARNING 記録する経過閾値 (ms)。
        """
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._threshold_ms = threshold_ms
        self._warning_threshold_ms = warning_threshold_ms
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        """監視を開始する。"""
        self._elapsed.start()
        self._timer.start()

    def stop(self) -> None:
        """監視を停止する。"""
        self._timer.stop()

    @Slot()
    def _on_tick(self) -> None:
        """tick ごとに前回 tick からの実経過を測って停滞判定へ渡す。"""
        elapsed_ms = self._elapsed.restart()
        self._check(elapsed_ms)

    def _check(self, elapsed_ms: int) -> None:
        """前回 tick からの経過を停滞閾値と比較し、超過ならログを出す。

        ``warning_threshold_ms`` 超過は WARNING、``threshold_ms`` 超過は DEBUG。
        短い停滞は規模が小さいだけの正常系でも起こりうるため WARNING にしない。

        Args:
            elapsed_ms: 前回 tick からの実経過 (ms)。
        """
        if elapsed_ms > self._warning_threshold_ms:
            logger.warning(
                f"メインスレッドのイベントループが約 {elapsed_ms} ms 停滞しました "
                f"(閾値 {self._warning_threshold_ms} ms, tick 間隔 {self._interval_ms} ms, #1221)。"
                "GUI が『応答なし』になった際の手掛かりです。"
            )
        elif elapsed_ms > self._threshold_ms:
            logger.debug(
                f"メインスレッドのイベントループが約 {elapsed_ms} ms 停滞しました "
                f"(閾値 {self._threshold_ms} ms, tick 間隔 {self._interval_ms} ms, #1596)。"
            )
